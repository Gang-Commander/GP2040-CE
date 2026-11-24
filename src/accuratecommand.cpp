#include "accuratecommand.h"

// See accuratecommand.h for the model. All times are microseconds and all
// comparisons are wrap-safe (uint32 micros wraps every ~71 minutes).

void AccurateCommand::configure(const AccurateCommandConfig& cfg) {
	config = cfg;

	// Clamp to the ranges exposed in the web configurator.
	if (config.thresholdUs < 1000)  config.thresholdUs = 1000;
	if (config.thresholdUs > 16000) config.thresholdUs = 16000;
	for (uint32_t& t : config.perStateThresholdUs) {
		if (t == 0) continue;              // 0 = follow the global threshold
		if (t < 1000)  t = 1000;
		if (t > 16000) t = 16000;
	}
	if (config.holdUs < 10000) config.holdUs = 10000;
	if (config.holdUs > 50000) config.holdUs = 50000;

	reset();
}

void AccurateCommand::reset() {
	head = 0;
	count = 0;
	dispStart = 0;
	lastRawState = 0;
	stateBeforeNeutral = 0;
}

void AccurateCommand::push(const Segment& s) {
	queue[(head + count) & (QUEUE_SIZE - 1)] = s;
	count++;
}

void AccurateCommand::pop() {
	head = (head + 1) & (QUEUE_SIZE - 1);
	count--;
}

// Drop the backlog and jump straight to the live raw state.
void AccurateCommand::flushToLive(uint32_t nowUs) {
	head = (head + count - 1) & (QUEUE_SIZE - 1);
	count = 1;
	dispStart = nowUs;
	flushCount++;
}

// Which state (if any) should be inserted between `prev` and `next`.
uint8_t AccurateCommand::assistInsertion(uint8_t prev, uint8_t next) const {
	if (config.hadokenAssist) {
		// 2 -> 6 / 2 -> 4  (236, 214): insert 3 / 1
		if (prev == DOWN && (next == RIGHT || next == LEFT))
			return DOWN | next;
		// 6 -> 2 / 4 -> 2  (632, 412): insert 3 / 1
		if (next == DOWN && (prev == RIGHT || prev == LEFT))
			return DOWN | prev;
	}
	if (config.shoryukenAssist) {
		// 6 -> 3 / 4 -> 1  (623, 421): insert 2
		if ((prev == RIGHT && next == (DOWN | RIGHT)) ||
		    (prev == LEFT  && next == (DOWN | LEFT)))
			return DOWN;
	}
	return 0;
}

// Time at which a closed (or synthetic) front segment stops being output.
void AccurateCommand::computeDisplayEnd(Segment& seg, uint32_t& dispEnd) {
	if (seg.synthetic) {
		dispEnd = dispStart + config.holdUs;
		return;
	}

	const uint32_t dur = seg.end - seg.start;
	const bool lagging = (int32_t)(dispStart - seg.start) > 0;
	uint32_t minShow;

	if (seg.state != 0 && dur < thresholdFor(seg.state)) {
		// Sub-threshold direction = noise. Pass through as-is when live,
		// drop it when we are behind (it would only add more lag).
		minShow = lagging ? 0 : dur;
	} else if (config.acEnabled && seg.state != 0) {
		// Valid direction: guarantee one full frame on the wire.
		minShow = config.holdUs;
	} else {
		// Neutral (never extended, never dropped: it separates dashes etc.)
		// or AC off: keep the original duration, capped so a long
		// segment can absorb the backlog.
		minShow = dur < config.holdUs ? dur : config.holdUs;
	}

	// Never stop before the segment's real end: this is what recovers the lag.
	dispEnd = dispStart + minShow;
	if (!timeReached(dispEnd, seg.end))
		dispEnd = seg.end;
}

uint8_t AccurateCommand::process(uint8_t dpad, uint32_t nowUs) {
	dpad &= DIR_MASK;

	if (!isActive())
		return dpad;

	// First call after reset: start the timeline.
	if (count == 0) {
		push({dpad, false, false, nowUs, 0});
		dispStart = nowUs;
		lastRawState = dpad;
		return dpad;
	}

	// 1) Record raw transitions.
	if (dpad != lastRawState) {
		const uint8_t prev = lastRawState;

		// The live (open) real segment is always the last element.
		Segment& live = back();
		live.closed = true;
		live.end = nowUs;
		const uint32_t dur = nowUs - live.start;

		if (config.acEnabled && prev != 0 &&
		    dur >= thresholdFor(prev) && dur < config.holdUs)
			holdCount++;

		// For assists, look through a short neutral: 2 -> (5) -> 6 counts as 2 -> 6.
		const uint8_t from = (prev == 0 && dur < config.thresholdUs) ? stateBeforeNeutral : prev;
		const uint8_t inserted = assistInsertion(from, dpad);

		const uint8_t needed = inserted ? 2 : 1;
		if (count + needed > QUEUE_SIZE) {
			// Backlog overflow: forget everything queued, restart from now.
			count = 0;
			dispStart = nowUs;
			flushCount++;
		}

		if (inserted) {
			push({inserted, true, true, nowUs, nowUs});
			assistCount++;
		}
		push({dpad, false, false, nowUs, 0});

		if (dpad == 0)
			stateBeforeNeutral = prev;
		lastRawState = dpad;
	}

	// 2) Advance the output through every segment whose display time is over.
	for (;;) {
		Segment& f = front();
		if (!f.closed && !f.synthetic)
			break; // live segment: shown until the raw state changes

		uint32_t dispEnd;
		computeDisplayEnd(f, dispEnd);
		if (!timeReached(nowUs, dispEnd))
			break;

		pop();
		dispStart = dispEnd;

		// Cap the backlog so lag can never accumulate.
		Segment& n = front();
		const uint32_t maxLagUs = config.holdUs * 2;
		if (!n.synthetic && (int32_t)(dispStart - n.start) > (int32_t)maxLagUs) {
			flushToLive(nowUs);
			break;
		}
	}

	return front().state;
}
