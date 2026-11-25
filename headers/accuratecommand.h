#ifndef _ACCURATE_COMMAND_H_
#define _ACCURATE_COMMAND_H_

#include <stdint.h>

/**
 * Accurate Command (AC) + motion assists.
 *
 * Operates on the SOCD-cleaned 4-bit dpad state (UP=1, DOWN=2, LEFT=4, RIGHT=8)
 * and has no hardware dependencies, so it can be unit tested on a host PC.
 *
 * Model
 * -----
 * The raw dpad stream is split into "segments": a run of time in which the
 * 8-way direction state does not change. The output replays these segments in
 * order, with three possible modifications:
 *
 *  1. Accurate Command:
 *     A hold-target segment that lasted >= threshold is shown for at least
 *     `hold` (default 18 ms = one 60 fps frame + 1 ms USB poll), so a 60 fps
 *     game is guaranteed to sample it at least once.
 *     Hold targets are, by default, only the states containing DOWN (2/3/1):
 *     the ones motion commands depend on. Other directions (walk, jump,
 *     dash) pass through with their real duration so they are never delayed
 *     by AC. `holdDownOnly = false` makes every non-neutral state a target.
 *     AC never creates a state that was not input; it only keeps a real
 *     state visible long enough to be read.
 *     Segments shorter than the threshold are passed through untouched when
 *     there is no backlog (zero added latency), and dropped when the output is
 *     lagging behind (they are noise and would only add more lag).
 *
 *  Separate feature (input completion; it DOES generate inputs):
 *  2. Hadoken assist (236/214/632/412):
 *     A direct DOWN <-> LEFT/RIGHT transition (optionally through a neutral
 *     shorter than the threshold) gets the missing down-diagonal inserted for
 *     `hold`. Up-side transitions are never touched (an up-diagonal is a jump).
 *
 *  3. Shoryuken assist (623/421):
 *     A direct RIGHT -> DOWN+RIGHT (LEFT -> DOWN+LEFT) transition gets DOWN
 *     inserted for `hold`.
 *
 * Holding/inserting a segment delays the segments after it. That delay is
 * recovered automatically: a long segment is only shown until its real end
 * time. The backlog is also capped (maxLagUs); beyond it the queue is flushed
 * to the live state so a chain of short inputs can never cause lasting lag.
 *
 * Buttons are intentionally NOT handled here: only directions are delayed.
 *
 * Cost: a handful of integer ops per call when nothing changes, so it is safe
 * to run on every iteration of the Core0 input loop.
 */

struct AccurateCommandConfig {
	bool acEnabled = true;
	bool holdDownOnly = true;      // hold only 2/3/1 (true) or every non-neutral state (false)
	bool hadokenAssist = false;
	bool shoryukenAssist = false;
	uint32_t thresholdUs = 9000;   // 1..16 ms (global; also used for neutral/noise checks)
	/**
	 * Optional per-direction thresholds, indexed by the 4-bit dpad state
	 * (e.g. [DOWN|RIGHT] for the down-right diagonal). 0 = use thresholdUs.
	 */
	uint32_t perStateThresholdUs[16] = {0};
	uint32_t holdUs = 18000;       // minimum on-screen time of a held/inserted state
};

class AccurateCommand {
public:
	static constexpr uint8_t UP    = 1U << 0;
	static constexpr uint8_t DOWN  = 1U << 1;
	static constexpr uint8_t LEFT  = 1U << 2;
	static constexpr uint8_t RIGHT = 1U << 3;
	static constexpr uint8_t DIR_MASK = UP | DOWN | LEFT | RIGHT;

	void configure(const AccurateCommandConfig& cfg);
	const AccurateCommandConfig& getConfig() const { return config; }

	/** True if at least one feature is on (otherwise process() is a pass-through). */
	bool isActive() const { return config.acEnabled || config.hadokenAssist || config.shoryukenAssist; }

	/**
	 * Feed the current SOCD-cleaned dpad and the current time; returns the dpad to send.
	 * Bits outside DIR_MASK are ignored.
	 */
	uint8_t process(uint8_t dpad, uint32_t nowUs);

	/** Forget all history (used on (re)configuration). Counters are kept. */
	void reset();

	// Debug counters (RAM only, reset on power cycle)
	uint32_t getHoldCount() const { return holdCount; }      // AC extensions
	uint32_t getAssistCount() const { return assistCount; }  // inserted diagonals/downs
	uint32_t getFlushCount() const { return flushCount; }    // backlog overflows
	void clearCounters() { holdCount = assistCount = flushCount = 0; }

private:
	struct Segment {
		uint8_t state;
		bool closed;      // raw state has already changed away from this one
		bool synthetic;   // inserted by an assist (not a real raw state)
		uint32_t start;   // raw start time (real segments)
		uint32_t end;     // raw end time (valid when closed)
	};

	static constexpr uint8_t QUEUE_SIZE = 8; // power of two

	Segment& at(uint8_t i) { return queue[(head + i) & (QUEUE_SIZE - 1)]; }
	Segment& front() { return at(0); }
	Segment& back() { return at(count - 1); }
	void push(const Segment& s);
	void pop();
	void flushToLive(uint32_t nowUs);
	void computeDisplayEnd(Segment& seg, uint32_t& dispEnd);
	uint8_t assistInsertion(uint8_t prev, uint8_t next) const;
	/** Whether AC may extend this state. */
	bool isHoldTarget(uint8_t state) const {
		return state != 0 && (!config.holdDownOnly || (state & DOWN));
	}
	/** Threshold for a given 8-way state (per-direction value if set, else global). */
	uint32_t thresholdFor(uint8_t state) const {
		const uint32_t t = config.perStateThresholdUs[state & DIR_MASK];
		return t ? t : config.thresholdUs;
	}

	static bool timeReached(uint32_t now, uint32_t t) { return (int32_t)(now - t) >= 0; }

	AccurateCommandConfig config;
	Segment queue[QUEUE_SIZE];
	uint8_t head = 0;
	uint8_t count = 0;

	uint32_t dispStart = 0;      // when the front segment started being output
	uint8_t lastRawState = 0;    // most recent raw state
	uint8_t stateBeforeNeutral = 0; // last non-neutral raw state (for short-neutral assists)
	uint32_t neutralStart = 0;

	uint32_t holdCount = 0;
	uint32_t assistCount = 0;
	uint32_t flushCount = 0;
};

#endif
