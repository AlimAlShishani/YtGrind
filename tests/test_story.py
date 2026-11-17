import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ytgrind import story, voice  # noqa: E402
from ytgrind.common import ToolError  # noqa: E402

EXAMPLE = Path(__file__).resolve().parent.parent / "templates" / "story.example.json"


def write(tmp: str, data: dict) -> Path:
    p = Path(tmp) / "story.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


class LoadTests(unittest.TestCase):
    def test_example_loads(self):
        st = story.load_story(EXAMPLE)
        self.assertEqual(len(st.scenes), 6)
        self.assertIn("Mia", st.scenes[0].characters)

    def test_errors_name_the_scene(self):
        with tempfile.TemporaryDirectory() as d:
            p = write(d, {"title": "x", "scenes": [{"narration": "ok"}, {"narration": " "}]})
            with self.assertRaisesRegex(ToolError, "Szene 2"):
                story.load_story(p)
            p = write(d, {"title": "x", "scenes": [{"narration": "ok", "characters": ["Nobody"]}]})
            with self.assertRaisesRegex(ToolError, "Nobody"):
                story.load_story(p)
            p = write(d, {"title": "x", "scenes": [{"narration": "ok", "motion": "spin"}]})
            with self.assertRaisesRegex(ToolError, "motion"):
                story.load_story(p)

    def test_scene_ranges(self):
        st = story.load_story(EXAMPLE)
        self.assertEqual([s.index for s in story.select_scenes(st, "2-4")], [2, 3, 4])
        self.assertEqual([s.index for s in story.select_scenes(st, "5")], [5])
        with self.assertRaises(ToolError):
            story.select_scenes(st, "9-12")


class PromptTests(unittest.TestCase):
    def test_prompt_includes_character_and_style(self):
        st = story.load_story(EXAMPLE)
        p = story.full_prompt(st, st.scenes[0])
        self.assertIn("green hoodie", p)
        self.assertIn("moody stylized", p)
        self.assertNotIn("Mia", story.full_prompt(st, st.scenes[1]))


class TimingTests(unittest.TestCase):
    def test_words_cover_duration_in_order(self):
        words = story.estimate_words("Hello there, this is a test. Done!", 6.0)
        self.assertEqual(len(words), 7)
        self.assertTrue(all(a["s"] < b["s"] for a, b in zip(words, words[1:])))
        self.assertLessEqual(words[-1]["e"], 6.0)
        self.assertGreater(words[-1]["e"], 5.0)

    def test_motions_alternate(self):
        st = story.load_story(EXAMPLE)
        m = [story.motion_for(st, s) for s in st.scenes]
        self.assertTrue(all(a != b for a, b in zip(m, m[1:])))
        self.assertIn("zoompan", story.motion_filter("zoom_in", 90, (1920, 1080)))


class CheckTests(unittest.TestCase):
    def test_flags_long_hook_and_uniform_scenes(self):
        scenes = [{"narration": " ".join(["word"] * 30), "image_prompt": f"p{i}"} for i in range(8)]
        with tempfile.TemporaryDirectory() as d:
            st = story.load_story(write(d, {"title": "t", "scenes": scenes}))
        notes = "\n".join(story.check(st))
        self.assertIn("HOOK", notes)
        self.assertIn("VARIANZ", notes)

    def test_compare_flags_same_opening(self):
        st = story.load_story(EXAMPLE)
        notes = "\n".join(story.check(st, compare=[st]))
        self.assertIn("TEMPLATE", notes)


class VoiceTests(unittest.TestCase):
    def test_request_shape(self):
        req = voice.build_elevenlabs_request("Hi", {"voice_id": "abc", "stability": 0.3}, "KEY")
        self.assertIn("/text-to-speech/abc", req.full_url)
        self.assertEqual(req.get_header("Xi-api-key"), "KEY")
        body = json.loads(req.data)
        self.assertEqual(body["text"], "Hi")
        self.assertEqual(body["voice_settings"]["stability"], 0.3)

    def test_missing_voice_id(self):
        with self.assertRaises(ToolError):
            voice.build_elevenlabs_request("Hi", {}, "KEY")

    def test_cache_key_depends_on_text_and_voice(self):
        a = voice.cache_key("one", {"voice_id": "x"}, "elevenlabs")
        self.assertNotEqual(a, voice.cache_key("two", {"voice_id": "x"}, "elevenlabs"))
        self.assertNotEqual(a, voice.cache_key("one", {"voice_id": "y"}, "elevenlabs"))
        self.assertEqual(a, voice.cache_key("one", {"voice_id": "x"}, "elevenlabs"))


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg fehlt")
class BuildSmokeTest(unittest.TestCase):
    def test_mock_build_and_cache(self):
        st = story.load_story(EXAMPLE)
        with tempfile.TemporaryDirectory() as d:
            out = Path(d)
            kw = dict(images_dir=out / "images", provider="mock", placeholder_images=True, encoder="x264")
            final = story.build(st, out, scenes_spec="1-2", **kw)
            self.assertTrue(final.exists() and final.stat().st_size > 0)
            # zweiter Lauf: Stimme komplett aus dem Cache
            story.build(st, out, scenes_spec="1-2", **kw)
            self.assertEqual(len(list((out / "work" / "audio").glob("*.mp3"))), 2)
            with self.assertRaises(ToolError):  # ohne Bilder und ohne Platzhalter -> klare Fehlermeldung
                story.build(st, out, images_dir=out / "none", provider="mock", encoder="x264")


if __name__ == "__main__":
    unittest.main()
