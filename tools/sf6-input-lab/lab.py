"""SF6 input lab — measure how Street Fighter 6 reads inputs, without mods.

    python lab.py ping             仮想コントローラーがスト6に届くか確認
    python lab.py setup            画面の読み取り位置を決める（初回のみ）
    python lab.py learn-icons      入力履歴のアイコンを自動で覚える
    python lab.py learn-moves      各技の画面の動きを覚える（実験C用）
    python lab.py run A            実験A: 短い斜めは読まれるか
    python lab.py run B            実験B: 1フレームに3方向
    python lab.py run C            実験C: 受付フレーム
    python lab.py report           結果をまとめる（data/report.md）
    python lab.py selftest         SF6なしで仕組みを確認（シミュレーション）
"""
from __future__ import annotations

import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sf6lab.core import Config  # noqa: E402
from sf6lab import experiments, report  # noqa: E402


def countdown(sec: int = 5) -> None:
    print(f"{sec}秒後に開始します。スト6のウィンドウをクリックして前面にしてください。")
    for i in range(sec, 0, -1):
        print(f"  {i}…")
        time.sleep(1)


def cmd_ping(args) -> None:
    from sf6lab.inject import VGamepadInjector, Step, play
    from sf6lab.core import D, R, L
    inj = VGamepadInjector()
    print("仮想コントローラーを接続しました。スト6のトレモで入力履歴を表示してください。")
    countdown()
    for st in [D, D | R, R, 0, L, 0]:
        play(inj, [Step(st, 300)])
    print("入力履歴に 2・3・6・4 が出ていれば成功です。出ない場合は README の「入力が届かないとき」を見てください。")
    inj.close()


def cmd_setup(args) -> None:
    from sf6lab.screen import Screen, select_rect
    cfg = Config.load()
    print("スト6のトレモで「入力履歴」を表示し、何度か方向を入力して履歴を数行ためてください。")
    input("準備ができたら Enter（5秒後に画面を撮ります）")
    time.sleep(5)
    shot = Screen().grab()
    r0 = select_rect(shot, "1. いちばん新しい行の方向アイコン")
    r1 = select_rect(shot, "2. その1つ前（2番目）の行の方向アイコン")
    cfg.icon_rect = r0
    cfg.row_step = [r1[0] - r0[0], r1[1] - r0[1]]
    cfg.action_rect = select_rect(shot, "3. 自キャラと、その前方（技が出るあたり）")
    cfg.save()
    print(f"保存しました: {Config.path()}")


def cmd_learn_icons(args) -> None:
    from sf6lab.rig import RealRig
    from sf6lab import history
    cfg = Config.load()
    rig = RealRig(cfg, need_history=False)
    countdown()
    history.learn_templates(cfg, rig.screen, rig.inj)
    print("完了。data/icons.npz に保存しました。")


def cmd_learn_moves(args) -> None:
    import numpy as np
    from sf6lab.rig import RealRig
    from sf6lab.inject import Step
    from sf6lab import outcome
    cfg = Config.load()
    rig = RealRig(cfg, need_history=False)
    print("リュウ（クラシック）、トレモの「SAゲージ無限」をONにして、初期位置で始めてください。")
    countdown()
    cents = {}
    for mv in outcome.MOVES:
        sigs = []
        for _ in range(args.n):
            rig.play([Step(0, 400)])
            rig.start_recording()
            log = rig.play(experiments.reference_steps(mv, cfg.attack_button) + [Step(0, 1100)])
            t_button = next(t for t, _, b in log if b)
            frames = rig.rec.stop()
            sigs.append(outcome.signature(frames, t_button))
            rig.play([Step(0, 50, (cfg.reset_button,)), Step(0, 900)])
        cents[mv] = np.mean(sigs, axis=0)
        print(f"  {outcome.LABEL[mv]} を記録（{len(frames)}枚/回）")
    outcome.save_model(cents)
    # sanity check: classify the references themselves
    print("確認: 覚えた技どうしの見分けやすさ（1.00に近いほど似ている）")
    for a in outcome.MOVES:
        print("  " + outcome.LABEL[a] + ": " + ", ".join(
            f"{outcome.LABEL[b]} {float(cents[a] @ cents[b] / (np.linalg.norm(cents[a]) * np.linalg.norm(cents[b]) + 1e-9)):.2f}"
            for b in outcome.MOVES if b != a))


def cmd_run(args) -> None:
    from sf6lab.rig import RealRig
    cfg = Config.load()
    rig = RealRig(cfg, need_history=args.exp in "AB", need_outcome=args.exp == "C")
    countdown()
    if args.exp == "A":
        path = experiments.run_A(rig, args.n)
    elif args.exp == "B":
        path = experiments.run_B(rig, args.n)
    else:
        path = experiments.run_C(rig, args.n, cfg)
    rig.inj.close()
    print(f"保存しました: {path}")


def cmd_report(args) -> None:
    print(report.build())


def cmd_selftest(args) -> None:
    """Run the experiments against a simulated game with a KNOWN model and
    buffers, and check the report recovers them. No SF6 / Windows needed."""
    import tempfile
    from sf6lab import core
    from sf6lab.rig import SimRig
    tmp = tempfile.mkdtemp()
    core.DATA_DIR = report.DATA_DIR = experiments.DATA_DIR = tmp
    ok = True
    for truth in ["strict", "queue", "single"]:
        rig = SimRig(truth, buffers={"hado": 11, "dp": 7, "tatsu": 11, "sa": 10})
        for f in os.listdir(tmp):
            os.remove(os.path.join(tmp, f))
        experiments.run_A(rig, args.n, out=os.path.join(tmp, "A_sim.csv"), progress=lambda *_: None)
        lines, a = report.report_A(report._latest("A"))
        hit = a["model"] == truth
        ok &= hit
        print(f"正解モデル {truth:6s} → 推定 {a['model']:6s} {'OK' if hit else 'NG'}")
    rig = SimRig("queue", buffers={"hado": 11, "dp": 7, "tatsu": 11, "sa": 10})
    cfg = Config()
    experiments.run_C(rig, 6, cfg, out=os.path.join(tmp, "C_sim.csv"), progress=lambda *_: None)
    _, est = report.report_C(report._latest("C"))
    print("受付フレームの推定:", est)
    print("selftest:", "OK" if ok else "NG")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ping").set_defaults(fn=cmd_ping)
    sub.add_parser("setup").set_defaults(fn=cmd_setup)
    sub.add_parser("learn-icons").set_defaults(fn=cmd_learn_icons)
    lm = sub.add_parser("learn-moves"); lm.add_argument("--n", type=int, default=4); lm.set_defaults(fn=cmd_learn_moves)
    r = sub.add_parser("run"); r.add_argument("exp", choices=["A", "B", "C"]); r.add_argument("--n", type=int, default=30); r.set_defaults(fn=cmd_run)
    sub.add_parser("report").set_defaults(fn=cmd_report)
    st = sub.add_parser("selftest"); st.add_argument("--n", type=int, default=40); st.set_defaults(fn=cmd_selftest)
    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
