"""The dashboard (--html): one self-contained page that fetches nothing when
opened and writes every name it is given as text.
"""

import json
import os
import re
import shutil
import unittest.mock

from helpers import Base, lay_out_three_harnesses, payload_of, record, slurp, tm


class TestDashboard(Base):
    """The dashboard has to be one self-contained file that works offline."""

    def render(self):
        self.write("a.jsonl", record("msg_1", out=900, read=50000, w1=2000))
        out = os.path.join(self.tmp, "d.html")
        overall, groups, meta, unknown = tm.collect(tm.transcripts(), ledger=False)
        tm.render_html(overall, groups, meta, unknown, "all time", out, covered="a window")
        return slurp(out, encoding="utf-8")

    def test_fetches_nothing_when_opened(self):
        """A file on disk must not depend on a network that may not be there."""
        page = self.render()
        self.assertNotIn("fonts.googleapis", page)
        self.assertNotIn("cdn.", page)
        self.assertNotIn("<script src", page)
        self.assertNotIn("<link rel=\"stylesheet\"", page)

    def test_fonts_are_embedded(self):
        page = self.render()
        self.assertIn("@font-face", page)
        self.assertIn("data:font/woff2;base64,", page)

    def test_survives_missing_font_files(self):
        """Deleting the fonts must degrade to system stacks, not crash."""
        real = tm.FONT_DIR
        tm.FONT_DIR = os.path.join(self.tmp, "no-fonts-here")
        try:
            page = self.render()
            self.assertNotIn("@font-face", page)
            self.assertIn("Georgia", page)   # the fallback stack is still there
        finally:
            tm.FONT_DIR = real

    def test_sections_are_numbered_in_page_order(self):
        """Tables were built before the page, so the first section read 03."""
        page = self.render()
        numbers = re.findall(r'<span class="no">(\d\d)</span>', page)
        self.assertEqual(numbers, [f"{i:02d}" for i in range(1, len(numbers) + 1)])
        self.assertNotIn("\u00a7NO\u00a7", page)

    def test_a_session_with_no_time_is_a_question_mark(self):
        """The empty "Last seen" cell was an em dash, the only dash character
        the engine printed; the terminal's sessions list has always said "?"."""
        self.write("a.jsonl", record("msg_1", out=900))
        out = os.path.join(self.tmp, "d.html")
        overall, groups, meta, unknown = tm.collect(tm.transcripts(), ledger=False)
        for info in meta.values():
            info["last"] = None
        tm.render_html(overall, groups, meta, unknown, "all time", out)
        page = slurp(out, encoding="utf-8")
        self.assertIn('<td class="dim">?</td>', page)
        self.assertNotIn(chr(0x2014), page)                 # the em dash

    def test_a_providers_name_cannot_write_markup(self):
        """Provider names come from import files, OpenCode and Codex logs. One
        named '"><img src=x onerror=alert(1)>' broke out of the chart legend's
        data-series attribute, and one named '</script><img src=x>' closed the
        dashboard's script early, twice; both ran as markup when opened."""
        hostile = ['</script><img src=x>', '"><img src=x onerror=alert(1)>']
        p = os.path.join(self.tmp, "events.jsonl")
        with open(p, "w") as f:
            for i, provider in enumerate(hostile + ["openai"]):
                f.write(json.dumps({"id": f"e{i}", "timestamp": "2026-09-20T10:00:00Z",
                                    "provider": provider, "model": "gpt-5",
                                    "input": 1000, "output": 500}) + "\n")
        tm._IMPORTS[:] = [p]
        tm._ONLY[:] = ["import"]
        out = os.path.join(self.tmp, "d.html")
        overall, groups, meta, unknown = tm.collect(tm.transcripts(), ledger=False)
        self.assertEqual(set(groups["provider"]), set(hostile) | {"openai"})
        tm.render_html(overall, groups, meta, unknown, "all time", out)
        page = slurp(out, encoding="utf-8")
        for raw in ("</script><img", 'data-series=""><img', "<img"):
            self.assertFalse(raw in page, raw)
        self.assertEqual(page.count("</script>"), 1)        # the dashboard's own
        self.assertIn('data-series="&quot;&gt;&lt;img src=x onerror=alert(1)&gt;"', page)
        series = payload_of(page)["views"]["all"]["series"]
        self.assertEqual({s["name"] for s in series}, set(hostile) | {"openai"})
        self.assertEqual({s["label"] for s in series} - {"OpenAI"}, set(hostile))

    def test_the_script_escapes_what_it_writes_as_markup(self):
        """The chart's tooltip put each series' label into innerHTML as it
        was. Every payload string now goes through esc() first."""
        js = tm.dashboard_asset("dashboard.js")
        self.assertIn("const esc = ", js)
        tip = js[js.index("const tip = host.querySelector('.tip');"):js.index("tip.classList.add('on')")]
        for raw in ("'<i>' + d.full", "+ s.label", "d.tokShort + ' tokens</i>"):
            self.assertNotIn(raw, tip)
        for escaped in ("esc(d.full)", "esc(s.label + ", "' · ' + d.tokShort + ' tokens')"):
            self.assertIn(escaped, tip)
        self.assertIn("pageId = esc(ACTIVE)", js)
        self.assertIn("esc(d.short)", js)

    def test_the_whole_window_is_named_for_the_run(self):
        """The fourth window tile always read "All time" and the rhythm
        section "Local time, all time", so a --period lastmonth page called
        its own month all time."""
        self.write("a.jsonl", record("msg_1", out=900))
        overall, groups, meta, unknown = tm.collect(tm.transcripts(), ledger=False)
        out = os.path.join(self.tmp, "d.html")

        def page(label):
            tm.render_html(overall, groups, meta, unknown, label, out)
            return slurp(out, encoding="utf-8")

        month = tm.period_label("lastmonth")                 # "September 2026"
        got = page(month)
        self.assertIn(f'<div class="win-k">{month}</div>', got)
        self.assertNotIn('<div class="win-k">All time</div>', got)
        self.assertIn(f"Local time, {month}. Spend", got)
        self.assertNotIn("Local time, all time", got)
        got = page("last 7d · <b>app</b>")
        self.assertIn('<div class="win-k">Last 7d · &lt;b&gt;app&lt;/b&gt;</div>', got)
        self.assertIn("Local time, last 7d · &lt;b&gt;app&lt;/b&gt;. Spend", got)
        got = page("all time")
        self.assertIn('<div class="win-k">All time</div>', got)
        self.assertIn("Local time, all time. Spend", got)

    def test_it_prints_every_section(self):
        """The dashboard printed blank pages: every section waits at opacity
        0 for the observer that reveals it as it scrolls into view, and
        paper never scrolls. A print block shows each part that starts
        hidden as it ends, hides what only works on a screen, keeps the page
        dark and keeps cards and rows whole. Printed straight after opening,
        the headline was part way through its count, so before a print every
        figure takes its final value."""
        page = self.render()
        self.assertTrue("@media print{" in page, "no print block")
        css = slurp(os.path.join(tm.DASH_DIR, "dashboard.css"), encoding="utf-8")
        screen, printed = css.split("@media print{")
        self.assertTrue(printed in page)
        screen, printed = (re.sub(r"/\*.*?\*/", "", part, flags=re.S) for part in (screen, printed))
        rules = {sel.strip(): decls for sel, decls in re.findall(r"([^{}]+)\{([^{}]*)\}", printed)}

        def rule_for(selector):
            return next((d for s, d in rules.items()
                         if selector in [p.strip() for p in s.split(",")]), "")

        # Every element the screen stylesheet starts hidden, shrunk or
        # blurred until a script or a scroll reveals it; the tooltip and the
        # crosshair only ever appear under the pointer.
        at_rest = set()
        for sel, decls in re.findall(r"([^{}]+)\{([^{}]*)\}", screen):
            if re.fullmatch(r"\s*(from|to|[\d.%,\s]+)\s*", sel):
                continue                                   # a keyframe
            if re.search(r"opacity:0(?![.\d])|scale[XY]\(0\)|translateY\(105%\)|blur\(", decls):
                at_rest.update(s.strip() for s in sel.split(","))
        at_rest -= {".tip", ".cross", ".knob"}
        self.assertTrue({".fade", "tbody tr", ".seg", ".win-bar", ".col", ".bar-cell i",
                         "h1 .ln>span", ".rule", "#sweep", ".big.settling"} <= at_rest, at_rest)
        for selector in sorted(at_rest):
            with self.subTest(selector=selector):
                decls = rule_for(selector)
                self.assertRegex(decls, r"display:none|opacity:1|scale[XY]\(1\)|transform:none")
        self.assertIn("display:none", rule_for("body::before"))
        for hidden in ("#sweep", ".pills", ".toggles"):       # .pills holds the harness picker
            self.assertIn("display:none", rule_for(hidden))
        self.assertIn("stroke-dasharray:none", rule_for(".cum"))
        everything = rule_for("*")
        self.assertIn("animation:none!important", everything)
        self.assertRegex(everything, r"(?<!-)print-color-adjust:exact")
        self.assertIn("-webkit-print-color-adjust:exact", everything)
        for whole in (".card", "tr"):
            self.assertIn("break-inside:avoid", rule_for(whole))
        self.assertTrue("addEventListener('beforeprint'" in page, "no beforeprint")

    def test_renders_with_no_history_at_all(self):
        """A fresh install opens the dashboard before it has priced anything."""
        out = os.path.join(self.tmp, "empty.html")
        overall, groups, meta, unknown = tm.collect([], ledger=False)
        tm.render_html(overall, groups, meta, unknown, "all time", out)
        self.assertIn("</html>", slurp(out, encoding="utf-8"))

    def test_a_missing_stylesheet_or_script_says_which(self):
        """The stylesheet and script moved out of the engine into dashboard/,
        and a page without either does not work. An install missing one
        stops with a single line naming the file and saying to reinstall,
        and writes no page."""
        self.write("a.jsonl", record("msg_1", out=900))
        result = tm.collect(tm.transcripts(), ledger=False)
        out = os.path.join(self.tmp, "d.html")
        for present, missing in (((), "dashboard.css"), (("dashboard.css",), "dashboard.js")):
            with self.subTest(missing=missing):
                folder = os.path.join(self.tmp, "dashboard-" + missing)
                os.makedirs(folder)
                for name in present:
                    shutil.copy(os.path.join(tm.DASH_DIR, name), folder)
                with unittest.mock.patch.object(tm, "DASH_DIR", folder), \
                        self.assertRaises(SystemExit) as e:
                    tm.render_html(*result, "all time", out)
                message = str(e.exception.code)
                self.assertIn(os.path.join("dashboard-" + missing, missing) + " is missing", message)
                self.assertIn("Reinstall Tokenmeter", message)
                self.assertEqual(len(message.splitlines()), 1)
                self.assertFalse(os.path.exists(out))
        # Both in place, the page carries them as they are on disk.
        tm.render_html(*result, "all time", out)
        page = slurp(out, encoding="utf-8")
        for name in ("dashboard.css", "dashboard.js"):
            text = slurp(os.path.join(tm.DASH_DIR, name), encoding="utf-8")
            self.assertIn(text.split("__PAYLOAD__")[-1], page)


class TestDashboardTokens(Base):
    """The dashboard gave each kind of token but never their total, nor how
    much of it the transcripts on disk still hold. A tile now gives total
    tokens by token_totals(), with fresh tokens under it, and a note under
    the tiles gives the report's kept and on-disk split whenever the ledger
    holds calls no transcript has any more."""

    def setUp(self):
        super().setUp()
        self.write("sess-a.jsonl", record("a1", ts="2026-09-01T12:00:00.000Z",
                                          inp=100, out=1000, read=4000, think=200))
        self.gone = self.write("sess-b.jsonl",
                               record("b1", ts="2026-09-02T12:00:00.000Z", out=2000, read=8000, w1=900),
                               record("b2", ts="2026-09-03T12:00:00.000Z", out=500, read=1500))

    def page(self, ledger=True):
        out = os.path.join(self.tmp, "d.html")
        overall, groups, meta, unknown = tm.collect(tm.transcripts(), ledger=ledger)
        tm.render_html(overall, groups, meta, unknown, "all time", out)
        return slurp(out, encoding="utf-8")

    def test_a_tile_gives_total_tokens_with_fresh_tokens_under_it(self):
        """Uncached input, cache writes, cache reads and output: 18,000, the
        200 thinking tokens already inside output. Fresh leaves out the
        13,500 cache reads."""
        page = self.page(ledger=False)
        # Beside the other tiles, in their markup, the subtitle under its label.
        self.assertIn('<div class="kpi"><b>3</b><span>API calls</span></div>'
                      '<div class="kpi"><b>18.0k</b><span>Total tokens</span>'
                      '<small>4.5k fresh</small></div>'
                      '<div class="kpi"><b>14.5k</b><span>Prompt tokens</span></div>', page)
        overall, *_ = tm.collect(tm.transcripts(), ledger=False)
        counted = tm.token_totals(overall["tokens"])
        self.assertEqual((counted["total"], counted["fresh"], counted["thinking"]), (18000, 4500, 200))

    def test_the_note_is_there_only_when_the_ledger_holds_what_no_transcript_does(self):
        """Every call on disk: kept and on disk are the same figure and there
        is no note. With a session's transcript deleted, the tile keeps its
        total and the note says how much of it only the ledger still has.
        Without the ledger nothing is kept, so there is no note either."""
        page = self.page()
        self.assertNotIn('class="kept-note"', page)
        self.assertIn("<b>18.0k</b><span>Total tokens</span>", page)
        os.remove(self.gone)
        page = self.page()
        self.assertIn("<b>18.0k</b><span>Total tokens</span>", page)
        self.assertIn('<p class="kept-note">Kept by the ledger 18.0k · on disk now 5.1k · '
                      "12.9k from 1 session whose transcripts are gone. Deleted sessions take "
                      "their transcripts with them; Tokenmeter keeps the record.</p>", page)
        self.assertEqual(page.count('class="kept-note"'), 1)
        page = self.page(ledger=False)
        self.assertNotIn('class="kept-note"', page)
        self.assertIn("<b>5.1k</b><span>Total tokens</span>", page)

    def test_the_tokens_chart_counts_the_same_total_ledger_only_days_included(self):
        """The Spend over time chart's Tokens view counts each day by
        token_totals() too, and a day whose transcript is gone is still a
        day of the chart, so its days add up to the tile."""
        self.page()
        os.remove(self.gone)
        days = payload_of(self.page())["views"]["all"]["days"]
        self.assertEqual([d["tokens"] for d in days], [5100, 10900, 2000])
        self.assertEqual(sum(d["tokens"] for d in days), 18000)
        days = payload_of(self.page(ledger=False))["views"]["all"]["days"]
        self.assertEqual([d["tokens"] for d in days], [5100])

    def test_the_charts_running_total_is_written_as_toks_writes_it(self):
        """In the Tokens view the tooltip's running total read "0M tokens"
        under half a million and dropped its decimals beside the day's own
        count, which the engine writes with toks(). The script's copy of
        toks() is checked against the engine's wherever node is installed."""
        js = tm.dashboard_asset("dashboard.js")
        tip = js[js.index("function onMove("):js.index("tip.classList.add('on')")]
        self.assertIn("toks(cum[i]) + ' tokens'", tip)
        self.assertNotIn("Math.round(cum[i] / 1e6)", tip)
        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        import subprocess
        counts = [0, 7, 999, 1000, 1049, 1050, 1250, 1350, 99_949, 99_950, 999_949, 999_950,
                  999_999, 1_000_000, 1_125_000, 1_135_000, 1_124_999, 1_015_000,
                  999_994_999, 999_995_000, 1_000_000_000, 1_125_000_000, 2_345_678_901]
        fn = js[js.index("function toks("):js.index("\n}\n", js.index("function toks(")) + 3]
        script = os.path.join(self.tmp, "toks.js")
        with open(script, "w", encoding="utf-8") as f:
            f.write(fn + "console.log(JSON.stringify(%s.map(toks)));\n" % json.dumps(counts))
        got = subprocess.run([node, script], capture_output=True, text=True, timeout=60)
        self.assertEqual(got.returncode, 0, got.stderr)
        self.assertEqual(json.loads(got.stdout), [tm.toks(n) for n in counts])

    def test_each_harness_page_gives_its_own_total(self):
        paths = lay_out_three_harnesses(self)
        whole, parts = tm.collect_views(paths, ledger=False)
        out = os.path.join(self.tmp, "d.html")
        tm.render_html(*whole.result(), "all time", out, views=tm.harness_pages(parts, paths))
        page = slurp(out, encoding="utf-8")
        views = re.findall(r'<div class="view" data-view="([^"]+)".*?<b>([^<]+)</b>'
                           r'<span>Total tokens</span><small>([^<]+) fresh</small>', page, re.S)
        want = {"all": whole.overall}
        want.update({name: part.overall for name, part in parts.items()})
        self.assertEqual(len(views), len(want))
        for name, total, fresh in views:
            with self.subTest(view=name):
                counted = tm.token_totals(want[name]["tokens"])
                self.assertEqual((total, fresh), (tm.toks(counted["total"]), tm.toks(counted["fresh"])))


if __name__ == "__main__":
    unittest.main(verbosity=2)
