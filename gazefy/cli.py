"""Gazefy CLI entry point."""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Gazefy: AI-driven screen automation")
    sub = parser.add_subparsers(dest="command")

    # --- learn (main UI: record + monitor + annotate + train) ---
    sub.add_parser("learn", help="Open the Gazefy control panel (record, monitor, annotate, train)")

    # --- task ---
    task_p = sub.add_parser("task", help="Execute a natural-language task on the screen")
    task_p.add_argument(
        "task", nargs="?", default="", help="Task description (omit for interactive)"
    )
    task_p.add_argument("--window", type=str, help="Window name to operate")
    task_p.add_argument("--region", type=str, help="Manual region: left,top,width,height")
    task_p.add_argument("--pack", type=str, default="", help="Force a specific pack name")
    task_p.add_argument("--packs-dir", type=str, default="packs")
    task_p.add_argument("--dry-run", action="store_true", help="Plan actions but do not execute")
    task_p.add_argument("--interactive", "-i", action="store_true", help="Read tasks from stdin")

    # --- replay ---
    replay_p = sub.add_parser("replay", help="Replay a recorded cursor trajectory")
    replay_p.add_argument("recording", help="Path to .jsonl recording file")
    replay_p.add_argument("--speed", type=float, default=1.0, help="Playback speed (2.0 = 2x)")

    # --- list-windows ---
    sub.add_parser("list-windows", help="List visible macOS windows")

    # --- benchmark ---
    bench_p = sub.add_parser("benchmark", help="Run capture + change detection benchmark")
    bench_p.add_argument("--window", type=str, help="Window name to benchmark")
    bench_p.add_argument("--region", type=str, help="Manual region: left,top,width,height")
    bench_p.add_argument("--duration", type=float, default=5.0, help="Duration in seconds")

    args = parser.parse_args(argv)

    if args.command == "learn":
        from gazefy.collector_ui.recorder_widget import main as learn_main

        learn_main()

    elif args.command == "task":
        import logging
        from pathlib import Path

        from gazefy.config import GazefyConfig
        from gazefy.core.orchestrator import Orchestrator
        from gazefy.core.task_runner import TaskRunner
        from gazefy.llm.interface import LLMInterface

        logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

        region = _resolve_region(args)
        cfg = GazefyConfig(region=region, dry_run=args.dry_run, window_name=args.window or "")
        orch = Orchestrator(cfg)
        orch.registry._packs_dir = Path(args.packs_dir)
        if args.pack:
            orch.router.force_pack(args.pack)

        orch.setup()
        runner = TaskRunner(orch, llm=LLMInterface())

        try:
            if args.interactive or not args.task:
                runner.run_interactive()
            else:
                result = runner.run(args.task)
                print("\n" + result.summary())
                sys.exit(0 if result.status == "success" else 1)
        finally:
            orch.shutdown()

    elif args.command == "replay":
        from gazefy.core.monitor import run_replay

        run_replay(args.recording, speed=args.speed)

    elif args.command == "list-windows":
        from gazefy.capture.window_finder import print_windows

        print("Visible windows:")
        print_windows()

    elif args.command == "benchmark":
        import importlib.util
        from pathlib import Path

        region = _resolve_region(args)
        script = Path(__file__).resolve().parent.parent / "scripts" / "benchmark.py"
        spec = importlib.util.spec_from_file_location("benchmark", script)
        bench = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(bench)

        bench.benchmark_capture(region, duration=args.duration)
        bench.benchmark_change_detection(region, num_frames=200)
        bench.benchmark_threaded_capture(region, duration=args.duration)
        print(f"\n{'=' * 60}\nBENCHMARK COMPLETE\n{'=' * 60}")

    else:
        parser.print_help()
        sys.exit(1)


def _resolve_region(args: argparse.Namespace):
    """Resolve capture region from --window or --region flags."""
    from gazefy.config import CaptureRegion

    if hasattr(args, "window") and args.window:
        from gazefy.capture.window_finder import find_window, print_windows

        w = find_window(args.window)
        if w is None:
            print(f"Window '{args.window}' not found. Available:")
            print_windows()
            sys.exit(1)
        return w.region

    if hasattr(args, "region") and args.region:
        parts = [int(x) for x in args.region.split(",")]
        return CaptureRegion(left=parts[0], top=parts[1], width=parts[2], height=parts[3])

    return CaptureRegion(left=100, top=100, width=800, height=600)


if __name__ == "__main__":
    main()
