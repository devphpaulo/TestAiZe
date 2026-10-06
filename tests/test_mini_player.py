from pathlib import Path
import unittest


class MiniPlayerContractTests(unittest.TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[1] / "src" / "testplayer"
        self.template = (root / "templates" / "player.html").read_text(encoding="utf-8")
        self.javascript = (root / "static" / "app.js").read_text(encoding="utf-8")
        self.styles = (root / "static" / "layout.css").read_text(encoding="utf-8")
        self.appearance = (root / "static" / "sleek.css").read_text(encoding="utf-8")

    def test_mini_player_reuses_player_state_and_has_pip_fallback(self):
        for fragment in (
            'id="mini-player-open"',
            'id="mini-player"',
            'aria-label="Mini Player da execução"',
            'id="mini-player-steps"',
            'id="mini-player-feedback" role="status"',
        ):
            self.assertIn(fragment, self.template)

        for fragment in (
            "documentPictureInPicture.requestWindow",
            "mainButton?.click()",
            "await uploadImage(area, file",
            "function syncObservedText(editor, value)",
            "if (node.matches('.rich-image')) return",
            "!node.querySelector('.rich-image')",
            "node.matches('p,div')",
            "input.ownerDocument.hasFocus()",
            "paste.addEventListener('input'",
            "paste.rows = 2",
            "pipWindow.document.title = 'TestAíZé - Mini Player'",
            "miniPlayerHome.append(miniPlayer)",
            "caseViewChangeHandlers.add(renderMiniPlayer)",
            "new MutationObserver(syncMiniPlayerTheme)",
            "miniPlayer.querySelector('#mini-player-close').focus()",
            "target?.focus()",
        ):
            self.assertIn(fragment, self.javascript)
        self.assertEqual(
            self.javascript.count("updateSummary();\n      renderMiniPlayer();\n      queueCase(view);"),
            2,
        )

        for selector in (
            ".mini-player",
            ".mini-player-statuses",
            ".mini-player-paste",
            ".mini-player-window .mini-player",
        ):
            self.assertIn(selector, self.styles)
        for status in ("nao_executado", "em_andamento", "bloqueado", "reprovado", "aprovado"):
            self.assertIn(f'.mini-player-step[data-status="{status}"]', self.styles + self.appearance)
            self.assertIn(f'.mini-player-status:hover[data-value="{status}"]', self.appearance)
        self.assertNotIn(".mini-player-step-summary:hover { box-shadow", self.styles)
        self.assertNotIn(".step-card.mini-player-source-active", self.styles)
        self.assertNotIn("syncActiveMiniStepMarker", self.javascript)
        self.assertIn("min-height: 64px", self.styles)
        self.assertIn("border-radius: var(--radius-md)", self.appearance)
        self.assertIn("TestaizeIcons.status(mainButton.dataset.value)", self.javascript)


if __name__ == "__main__":
    unittest.main()
