"""Exercise the release feed checks before publication."""

import importlib.util
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location(
    "validate_appcast", Path(__file__).with_name("validate-appcast.py")
)
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)

URL = "https://github.com/ZimengXiong/winmux/releases/download/v0.5.3/WinMux-0.5.3.zip"
ITEM = f"""<item>
<sparkle:version>0.5.3</sparkle:version>
<sparkle:shortVersionString>0.5.3</sparkle:shortVersionString>
<enclosure url="{URL}" length="100" sparkle:edSignature="test-signature"/>
</item>"""


class AppcastValidationTest(unittest.TestCase):
    def validate(self, items):
        with tempfile.TemporaryDirectory() as directory:
            feed = Path(directory) / "appcast.xml"
            feed.write_text(
                '<rss xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle">'
                f"<channel>{items}</channel></rss>"
            )
            validator.validate_appcast(feed, "0.5.3", URL)

    def test_current_release_is_accepted(self):
        self.validate(ITEM)

    def test_stale_archive_cannot_add_phantom_update(self):
        with self.assertRaisesRegex(ValueError, "exactly one"):
            self.validate(ITEM + ITEM.replace("0.5.3", "1.0"))

    def test_wrong_version_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "version"):
            self.validate(ITEM.replace(
                "<sparkle:version>0.5.3", "<sparkle:version>1"
            ))

    def test_wrong_archive_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "current release archive"):
            self.validate(ITEM.replace("WinMux-0.5.3.zip", "WinMux-0.5.1.zip"))

    def test_unsigned_archive_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "signature"):
            self.validate(ITEM.replace('sparkle:edSignature="test-signature"', ""))


if __name__ == "__main__":
    unittest.main()
