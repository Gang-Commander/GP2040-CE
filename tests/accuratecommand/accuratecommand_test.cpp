// Host-side tests and simulation for AccurateCommand.
//
// Build & run (no Pico SDK needed):
//   g++ -std=c++17 -O2 -I../../headers ../../src/accuratecommand.cpp accuratecommand_test.cpp -o ac_test && ./ac_test
//
// Part 1: deterministic scenario checks (assert-style, exit code != 0 on failure).
// Part 2: Monte Carlo — how often a 60 fps game (1000 Hz USB poll, random phase)
//         actually sees a short diagonal, with AC off vs on.

#include "accuratecommand.h"
#include <cstdio>
#include <cstdlib>
#include <cstdint>
#include <random>
#include <string>
#include <vector>

using AC = AccurateCommand;
static const uint8_t U = AC::UP, D = AC::DOWN, L = AC::LEFT, R = AC::RIGHT;

static int failures = 0;
#define CHECK(cond, ...) do { if (!(cond)) { failures++; std::printf("  FAIL %s:%d: ", __FILE__, __LINE__); std::printf(__VA_ARGS__); std::printf("\n"); } } while (0)

// Numpad notation for readable output.
static char numpad(uint8_t s) {
	switch (s) {
		case 0: return '5'; case U: return '8'; case D: return '2'; case L: return '4'; case R: return '6';
		case U|L: return '7'; case U|R: return '9'; case D|L: return '1'; case D|R: return '3';
		default: return '?';
	}
}

struct Change { uint32_t t; uint8_t s; };

// Raw input script: list of (state, duration_us). Simulates a fast loop.
struct Sim {
	AC ac;
	uint32_t t0;
	uint32_t step;
	std::vector<Change> out; // output change log

	Sim(AccurateCommandConfig cfg, uint32_t start = 1000000, uint32_t stepUs = 50)
	    : t0(start), step(stepUs) { ac.configure(cfg); }

	void run(const std::vector<std::pair<uint8_t, uint32_t>>& script, uint32_t tailUs = 100000) {
		uint32_t t = t0;
		for (auto& p : script) {
			uint32_t end = t + p.second;
			for (; (int32_t)(end - t) > 0; t += step) record(t, ac.process(p.first, t));
		}
		uint8_t last = script.back().first;
		uint32_t end = t + tailUs;
		for (; (int32_t)(end - t) > 0; t += step) record(t, ac.process(last, t));
	}
	void record(uint32_t t, uint8_t s) {
		if (out.empty() || out.back().s != s) out.push_back({t, s});
	}
	std::string seq() const { std::string r; for (auto& c : out) r += numpad(c.s); return r; }
	// Duration the output spent in the i-th change.
	uint32_t durOf(size_t i) const { return i + 1 < out.size() ? out[i + 1].t - out[i].t : 0; }
	uint32_t rel(size_t i) const { return out[i].t - t0; }
};

static AccurateCommandConfig cfg(bool ac, bool hado = false, bool sho = false, uint32_t thrMs = 9) {
	AccurateCommandConfig c;
	c.acEnabled = ac; c.hadokenAssist = hado; c.shoryukenAssist = sho;
	c.thresholdUs = thrMs * 1000; c.holdUs = 18000;
	return c;
}

static void scenarios() {
	std::printf("== Scenarios\n");

	{ // Disabled => exact pass-through
		Sim s(cfg(false));
		s.run({{D, 30000}, {D|R, 5000}, {R, 30000}});
		CHECK(s.seq() == "236", "pass-through got %s", s.seq().c_str());
		CHECK(s.durOf(1) == 5000, "3 should stay 5ms, got %u", s.durOf(1));
	}
	{ // AC: valid short diagonal (10ms) is held to 18ms, then 6 follows
		Sim s(cfg(true));
		s.run({{D, 30000}, {D|R, 10000}, {R, 30000}});
		CHECK(s.seq() == "236", "got %s", s.seq().c_str());
		CHECK(s.durOf(1) >= 18000 && s.durOf(1) <= 18100, "3 held %u us", s.durOf(1));
		CHECK(s.rel(2) >= 48000 && s.rel(2) <= 48100, "6 delayed to %u", s.rel(2));
		CHECK(s.ac.getHoldCount() == 1, "holdCount %u", s.ac.getHoldCount());
	}
	{ // AC: sub-threshold diagonal (5ms) passes through unchanged, no delay
		Sim s(cfg(true));
		s.run({{D, 30000}, {D|R, 5000}, {R, 30000}});
		CHECK(s.seq() == "236", "got %s", s.seq().c_str());
		CHECK(s.durOf(1) == 5000, "3 should stay 5ms, got %u", s.durOf(1));
		CHECK(s.ac.getHoldCount() == 0, "holdCount %u", s.ac.getHoldCount());
	}
	{ // AC: long inputs are not touched (no added latency at all)
		Sim s(cfg(true));
		s.run({{D, 30000}, {D|R, 25000}, {R, 30000}});
		CHECK(s.rel(1) == 30000 && s.rel(2) == 55000, "timing changed: %u %u", s.rel(1), s.rel(2));
	}
	{ // Default (down-only): non-down directions are never held (walk/dash/jump untouched)
		Sim s(cfg(true));
		s.run({{0, 30000}, {R, 12000}, {0, 8000}, {R, 30000}});
		CHECK(s.seq() == "5656", "dash got %s", s.seq().c_str());
		CHECK(s.durOf(1) == 12000, "6 should stay 12ms, got %u", s.durOf(1));
		Sim s2(cfg(true));
		s2.run({{0, 30000}, {U|R, 10000}, {0, 30000}});
		CHECK(s2.durOf(1) == 10000, "9 should stay 10ms, got %u", s2.durOf(1));
		CHECK(s.ac.getHoldCount() == 0 && s2.ac.getHoldCount() == 0, "holdCount should be 0");
	}
	{ // Default (down-only): 623 with a short 2 -> the 2 is held, the 6 before it is not
		Sim s(cfg(true));
		s.run({{R, 10000}, {D, 10000}, {D|R, 30000}});
		CHECK(s.seq() == "623", "got %s", s.seq().c_str());
		CHECK(s.durOf(0) == 10000, "6 should stay 10ms, got %u", s.durOf(0));
		CHECK(s.durOf(1) >= 18000 && s.durOf(1) <= 18100, "2 held %u", s.durOf(1));
	}
	{ // All-direction mode: neutral is never extended or dropped (dash 6,5,6 survives)
		AccurateCommandConfig c = cfg(true); c.holdDownOnly = false;
		Sim s(c);
		s.run({{0, 30000}, {R, 12000}, {0, 8000}, {R, 30000}});
		CHECK(s.seq() == "5656", "dash got %s", s.seq().c_str());
		CHECK(s.durOf(1) >= 18000, "first 6 held %u", s.durOf(1));
		CHECK(s.durOf(2) == 8000, "neutral kept 8ms, got %u", s.durOf(2));
	}
	{ // Hadoken assist: direct 2 -> 6 gets 3 inserted for 18 ms
		Sim s(cfg(false, true));
		s.run({{D, 30000}, {R, 30000}});
		CHECK(s.seq() == "236", "got %s", s.seq().c_str());
		CHECK(s.durOf(1) >= 18000 && s.durOf(1) <= 18100, "inserted 3 %u", s.durOf(1));
	}
	{ // Hadoken assist: mirrored 2 -> 4 => 1, and 2 -> short neutral -> 6
		Sim s(cfg(false, true));
		s.run({{D, 30000}, {L, 30000}});
		CHECK(s.seq() == "214", "got %s", s.seq().c_str());
		Sim s2(cfg(true, true));
		s2.run({{D, 30000}, {0, 3000}, {R, 30000}});
		CHECK(s2.seq() == "2536", "short neutral got %s", s2.seq().c_str());
	}
	{ // Hadoken assist: up-side transitions are never touched (no accidental jump)
		Sim s(cfg(false, true, true));
		s.run({{L, 30000}, {U, 30000}, {R, 30000}});
		CHECK(s.seq() == "486", "got %s", s.seq().c_str());
	}
	{ // Shoryuken assist: 6 -> 3 gets 2 inserted; 4 -> 1 mirrored
		Sim s(cfg(false, false, true));
		s.run({{R, 30000}, {D|R, 30000}});
		CHECK(s.seq() == "623", "got %s", s.seq().c_str());
		Sim s2(cfg(false, false, true));
		s2.run({{L, 30000}, {D|L, 30000}});
		CHECK(s2.seq() == "421", "got %s", s2.seq().c_str());
	}
	{ // Backlog is bounded: very fast alternating inputs, then the output
	  // must converge to the live state within a few frames.
		Sim s(cfg(true, true, true));
		std::vector<std::pair<uint8_t, uint32_t>> script;
		const uint8_t cyc[] = {D, D|R, R, D|R};
		for (int i = 0; i < 200; i++) script.push_back({cyc[i % 4], 9500});
		script.push_back({0, 1});
		s.run(script, 200000);
		const uint32_t settle = s.out.back().t - (s.t0 + 200 * 9500);
		CHECK(s.out.back().s == 0 && settle <= 3 * 18000, "settle %u us", settle);
	}
	{ // Per-direction threshold: down-right at 5 ms, everything else at the global 9 ms
		AccurateCommandConfig c = cfg(true);
		c.perStateThresholdUs[D|R] = 5000;
		Sim s(c);
		s.run({{D, 30000}, {D|R, 6000}, {R, 30000}});
		CHECK(s.durOf(1) >= 18000, "3 (6ms) should be held with 5ms threshold, got %u", s.durOf(1));
		Sim s2(c);
		s2.run({{D, 30000}, {D|L, 6000}, {L, 30000}});
		CHECK(s2.durOf(1) == 6000, "1 (6ms) should pass through with global 9ms, got %u", s2.durOf(1));
	}
	{ // micros() wrap-around
		Sim s(cfg(true), 0xFFFFFFFFu - 20000);
		s.run({{D, 15000}, {D|R, 10000}, {R, 30000}});
		CHECK(s.seq() == "236", "wrap got %s", s.seq().c_str());
		CHECK(s.durOf(1) >= 18000 && s.durOf(1) <= 18100, "wrap hold %u", s.durOf(1));
	}
	std::printf("  %s\n", failures ? "FAILED" : "all passed");
}

// Output state at absolute time t from a change log.
static uint8_t stateAt(const std::vector<Change>& log, uint32_t t) {
	uint8_t s = 0;
	for (auto& c : log) { if ((int32_t)(c.t - t) > 0) break; s = c.s; }
	return s;
}

static void monteCarlo() {
	std::printf("\n== Monte Carlo: chance a 60fps game sees the diagonal of 2 -> 3 -> 6\n");
	std::printf("   (1000Hz USB poll, random frame/poll phase, 4000 trials each)\n");
	std::printf("   diag_ms | AC off | AC on (thr 9ms) | AC on (thr 6ms)\n");
	std::mt19937 rng(12345);
	const uint32_t frame = 16667;
	for (uint32_t d = 2; d <= 18; d += 2) {
		double seen[3] = {0, 0, 0};
		const int trials = 4000;
		AccurateCommandConfig cs[3] = {cfg(false), cfg(true, false, false, 9), cfg(true, false, false, 6)};
		for (int k = 0; k < 3; k++) {
			for (int i = 0; i < trials; i++) {
				Sim s(cs[k], 1000000, 100);
				s.run({{D, 40000}, {D|R, d * 1000}, {R, 60000}}, 0);
				const uint32_t framePhase = rng() % frame;
				const uint32_t pollPhase = rng() % 1000;
				bool hit = false;
				for (uint32_t T = s.t0 + framePhase; (int32_t)(s.t0 + 140000 - T) > 0; T += frame) {
					// The host only has the report from the latest 1ms poll.
					uint32_t poll = T - ((T - pollPhase) % 1000);
					if (stateAt(s.out, poll) == (D|R)) { hit = true; break; }
				}
				seen[k] += hit;
			}
		}
		std::printf("   %7u | %5.0f%% | %14.0f%% | %14.0f%%\n", d,
		            100 * seen[0] / trials, 100 * seen[1] / trials, 100 * seen[2] / trials);
	}
}

int main() {
	scenarios();
	monteCarlo();
	return failures ? 1 : 0;
}
