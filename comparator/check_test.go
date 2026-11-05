package comparatorcheck

// Runs the built comparator through the node's own runner
// (pkg/wasm/runtime.NewDeterministic) and compares every score with the
// node's answer key (pkg/scoring/comparator.ReferenceScore).
//
//	cargo build --release --target wasm32-unknown-unknown
//	go test ./work/comparator/ -v

import (
	"context"
	"fmt"
	"math"
	"math/rand"
	"os"
	"testing"

	"github.com/telegraphprotocol/telegraph-wasm-baseline/pkg/scoring/comparator"
	"github.com/telegraphprotocol/telegraph-wasm-baseline/pkg/wasm/runtime"
	"github.com/tetratelabs/wazero"
)

const wasmPath = "target/wasm32-unknown-unknown/release/cpv_comparator.wasm"

func TestComparatorMatchesReference(t *testing.T) {
	ctx := context.Background()
	bin, err := os.ReadFile(wasmPath)
	if err != nil {
		t.Fatalf("build first: %v", err)
	}

	// The node requires zero imports (wasm32-unknown-unknown, not WASI).
	rt := wazero.NewRuntime(ctx)
	cm, err := rt.CompileModule(ctx, bin)
	if err != nil {
		t.Fatal(err)
	}
	if n := len(cm.ImportedFunctions()) + len(cm.ImportedMemories()); n != 0 {
		t.Fatalf("module has %d imports, want 0", n)
	}
	_ = rt.Close(ctx)

	run, err := runtime.NewDeterministic(ctx, bin)
	if err != nil {
		t.Fatal(err)
	}
	defer run.Close(ctx)

	score := func(code, tol, truth, miner int64) int64 {
		s, err := run.ScoreDeterministic(ctx, miner, truth, [2]int64{code, tol})
		if err != nil {
			return -1 // rejection; must line up with a negative reference
		}
		return int64(s)
	}
	want := func(code, tol, truth, miner int64) int64 {
		r := comparator.ReferenceScore(code, tol, truth, miner)
		if r < 0 || r > 10000 {
			return -1
		}
		return r
	}

	codes := []int64{0, 1, 2, 3, 4, -1, 1<<32 + 1, 1<<32 + 2, math.MaxInt64}
	tols := []int64{0, 1, 2, 5, 50, 100, 150, 800, 10000, -5, math.MaxInt64 / 2, math.MaxInt64}
	truths := []int64{0, 1, -1, 7, 100, 12345, 1e6, 1e12, 1e18, -1e18, math.MaxInt64, math.MinInt64}

	cases, mismatches := 0, 0
	check := func(code, tol, truth, miner int64) {
		if truth == 0 {
			return // the node never scores a zero truth: it means ground truth was not fetched
		}
		cases++
		got, exp := score(code, tol, truth, miner), want(code, tol, truth, miner)
		if got != exp {
			mismatches++
			if mismatches <= 10 {
				t.Errorf("code=%d tol=%d truth=%d miner=%d: got %d want %d", code, tol, truth, miner, got, exp)
			}
		}
	}
	for _, code := range codes {
		for _, tol := range tols {
			for _, truth := range truths {
				// AbsTol points, and the same points scaled for RelTol (tol bps of truth).
				rel := truth / 10000 * tol
				for _, d := range []int64{0, 1, tol / 2, tol, 2*tol - 1, 2 * tol, 2*tol + 1, 3 * tol,
					rel / 2, rel, 2 * rel, 2*rel + 1, math.MaxInt64, math.MinInt64} {
					check(code, tol, truth, truth+d)
					check(code, tol, truth, truth-d)
				}
			}
		}
	}
	rng := rand.New(rand.NewSource(1))
	for i := 0; i < 200000; i++ {
		code := int64(rng.Intn(5))
		tol := rng.Int63n(20000)
		truth := rng.Int63() >> uint(rng.Intn(63))
		if rng.Intn(2) == 0 {
			truth = -truth
		}
		check(code, tol, truth, truth+rng.Int63n(4*tol+3)-2*tol-1)
	}
	t.Logf("%d cases, %d mismatches", cases, mismatches)

	// Determinism: a second pass must give identical bits.
	for _, truth := range truths {
		for _, tol := range tols {
			a, b := score(2, tol, truth, truth+tol), score(2, tol, truth, truth+tol)
			if a != b {
				t.Fatalf("non-deterministic: %d vs %d", a, b)
			}
		}
	}
}

// Writes reference cases for the endpoint test (worker/check.mjs).
func TestWriteEndpointFixture(t *testing.T) {
	f, err := os.Create("worker/fixture.txt")
	if err != nil {
		t.Fatal(err)
	}
	defer f.Close()
	rng := rand.New(rand.NewSource(7))
	for i := 0; i < 3000; i++ {
		code, tol := int64(rng.Intn(5)), rng.Int63n(20000)
		truth := rng.Int63() >> uint(rng.Intn(63))
		if truth == 0 {
			truth = 1e18
		}
		miner := truth + rng.Int63n(4*tol+3) - 2*tol - 1
		fmt.Fprintf(f, "%d %d %d %d %d\n", code, tol, truth, miner, comparator.ReferenceScore(code, tol, truth, miner))
	}
}
