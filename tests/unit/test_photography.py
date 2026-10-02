"""photography: photo request, refusal, analysis, large or odd images, errors."""
import base64
import hashlib
import io
import random
import tempfile
import unittest
from pathlib import Path

from PIL import Image

try:
    from . import helpers
except ImportError:
    import helpers

from src.agents import intake
from src.agents.intake import NO_PHOTO_PATTERN, _prepare_image

OK = {"lesion_type": "escoriazione", "description": "Escoriazione superficiale sull'avambraccio."}
NOT_ASSESSABLE = {"lesion_type": "NON VALUTABILE", "description": "NON VALUTABILE"}


def _md5(path):
    """HELPER _md5: fingerprint of a file, to prove the original is never modified."""
    return hashlib.md5(Path(path).read_bytes()).hexdigest()


def _decode(b64):
    """HELPER _decode: opens the base64 image sent to the vision model."""
    return Image.open(io.BytesIO(base64.b64decode(b64)))


class Images(unittest.TestCase):
    """HELPER Images: creates the test images in a temporary folder."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        d = Path(cls._tmp.name)
        cls.small_jpg = d / "small.jpg"
        Image.new("RGB", (225, 225), (200, 120, 110)).save(cls.small_jpg)
        cls.small_png = d / "small.png"
        Image.new("RGB", (225, 225), (200, 120, 110)).save(cls.small_png)
        cls.small_bmp = d / "small.bmp"
        Image.new("RGB", (120, 80), (200, 120, 110)).save(cls.small_bmp)
        # Phone-style photo: stored 300x200, EXIF says "rotate 90 degrees".
        cls.rotated_jpg = d / "rotated.jpg"
        exif = Image.Exif()
        exif[0x0112] = 6
        Image.new("RGB", (300, 200), (200, 120, 110)).save(cls.rotated_jpg, exif=exif)
        # Pure noise (not compressible): ~6.7 MB, above the provider limit.
        side = 1500
        large = Image.frombytes("RGB", (side, side), random.Random(0).randbytes(side * side * 3))
        cls.large_png = d / "large.png"
        large.save(cls.large_png)
        cls.pdf = d / "document.pdf"
        cls.pdf.write_bytes(b"%PDF-1.4 not an image")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()


class TestImagePreparation(Images):
    def test_small_images_sent_as_they_are_with_the_real_type(self):
        """TEST image preparation: small JPEG/PNG are sent unchanged with their real MIME type."""
        for path, mime in ((self.small_jpg, "image/jpeg"), (self.small_png, "image/png")):
            with self.subTest(file=path.name):
                before = _md5(path)
                b64, kind = _prepare_image(str(path))
                self.assertEqual(kind, mime)
                self.assertEqual(base64.b64decode(b64), path.read_bytes())
                self.assertEqual(_md5(path), before)

    def test_large_image_reduced_and_original_untouched(self):
        """TEST image preparation: a too-large image is sent as a smaller JPEG copy, the original is unchanged."""
        before = _md5(self.large_png)
        b64, kind = _prepare_image(str(self.large_png))
        self.assertEqual(kind, "image/jpeg")
        self.assertLessEqual(len(b64), intake.MAX_IMAGE_BASE64_BYTES)
        self.assertEqual(_md5(self.large_png), before)

    def test_non_image_or_missing_file(self):
        """TEST image preparation: a PDF or a missing file returns None."""
        self.assertIsNone(_prepare_image(str(self.pdf)))
        self.assertIsNone(_prepare_image(str(self.pdf.with_name("missing.jpg"))))

    def test_unsupported_format_converted_to_jpeg(self):
        """TEST image preparation: a small BMP (format not accepted by the provider) is converted to JPEG."""
        b64, kind = _prepare_image(str(self.small_bmp))
        self.assertEqual(kind, "image/jpeg")
        self.assertEqual(_decode(b64).format, "JPEG")

    def test_exif_rotation_applied_to_the_copy(self):
        """TEST image preparation: when a copy is made, the EXIF rotation is applied so the photo is upright."""
        before = _md5(self.rotated_jpg)
        with helpers.mock.patch.object(intake, "MAX_IMAGE_BASE64_BYTES", 100):  # force the copy
            b64, _ = _prepare_image(str(self.rotated_jpg))
        self.assertEqual(_decode(b64).size, (200, 300))
        self.assertEqual(_md5(self.rotated_jpg), before)


class TestRefusal(unittest.TestCase):
    def test_refusal_words(self):
        """TEST photo refusal: the usual ways of saying "no photo" are recognized."""
        for t in ("no", "no grazie", "nessuna foto", "niente", "non ho foto", "non serve", "non c'è", "non c’è",
                  "salta", "prosegui", "procedi", "avanti", "senza foto", "skip"):
            with self.subTest(t=t):
                self.assertTrue(NO_PHOTO_PATTERN.match(t))

    def test_not_refusals(self):
        """TEST photo refusal: ordinary sentences containing "no" are not refusals."""
        for t in ("sono qui", "buongiorno", "nota: il paziente e' agitato"):
            with self.subTest(t=t):
                self.assertFalse(NO_PHOTO_PATTERN.match(t))


class StopAtSupervisor(Exception):
    pass


class TestPhotography(helpers.VitaTestCase, Images):
    """The supervisor is replaced by a fake one that stops at once: here only reaching it matters, and with which photo."""

    def setUp(self):
        super().setUp()
        self.supervisor = []

        async def fake_supervisor(state):
            self.supervisor.append(state.patient_card.symptom.photo)
            raise StopAtSupervisor()

        p = helpers.mock.patch.object(helpers.graph, "supervisor_node", fake_supervisor)
        p.start()
        self.addCleanup(p.stop)
        self.conv = helpers.Conversation(self)
        helpers.go_to_photo(self.conv)

    def send(self, *args, **kwargs):
        """HELPER send: like Conversation.send, stopping silently at the fake supervisor."""
        try:
            self.conv.send(*args, **kwargs)
        except StopAtSupervisor:
            pass

    def test_photo_request_arrives_immediately(self):
        """TEST photography: the photo is requested right after the symptoms are confirmed."""
        self.assertIn("È disponibile una foto della zona interessata", self.last_message())

    def test_no_goes_straight_to_the_supervisor(self):
        """TEST photography: "no" goes on to the supervisor without another pause."""
        self.send("no")
        self.assertIn("Nessuna foto", self.messages_from("Fotografia")[0])
        self.assertEqual(len(self.supervisor), 1)

    def test_any_other_message_asks_again(self):
        """TEST photography: a message that is neither a photo nor a refusal asks for the photo again."""
        self.send("aspetta un attimo")
        self.assertIn("È disponibile una foto", self.last_message())
        self.assertEqual(self.supervisor, [])

    def test_photo_analysed(self):
        """TEST photography: an attached photo is analysed, shown and passed on to the supervisor."""
        self.send("ecco la foto", photo=self.small_png, vision=[OK])
        self.assertIn("**Foto**", self.messages_from("Fotografia")[0])
        self.assertIn("**Tipo** escoriazione", self.messages_from("Fotografia")[0])
        self.assertEqual(self.supervisor[0].injury_type, "escoriazione")

    def test_not_assessable_photo_is_asked_again(self):
        """TEST photography: a NON VALUTABILE photo is removed and another one is requested."""
        self.send("questa", photo=self.small_jpg, vision=[NOT_ASSESSABLE])
        self.assertIn("Foto non valutabile", self.last_message())
        self.assertIsNone(self.conv.card["symptom"]["photo"])
        self.assertEqual(self.supervisor, [])

    def test_vision_model_error(self):
        """TEST photography: a vision model error goes on without the photo."""
        self.send("ecco", photo=self.small_png, vision=[RuntimeError("vision unavailable")])
        self.assertIn("Si procede senza foto", self.messages_from("Fotografia")[0])
        self.assertIsNone(self.supervisor[0])

    def test_non_image_file(self):
        """TEST photography: a file that is not an image goes on without the photo."""
        self.send("ecco", photo=self.pdf)
        self.assertIn("Impossibile aprire l'immagine", self.messages_from("Fotografia")[0])
        self.assertIsNone(self.supervisor[0])

    def test_no_caption_with_an_attached_photo_is_still_analysed(self):
        """TEST photography: an attached photo wins over a caption that starts with "no"."""
        self.send("no, non è grave ma eccola", photo=self.small_png, vision=[OK])
        self.assertEqual(len(self.vision.calls), 1)
        self.assertEqual(self.supervisor[0].injury_type, "escoriazione")

    def test_two_not_assessable_photos_then_no(self):
        """TEST photography: after two unusable photos, "no" still goes on to the supervisor without a photo."""
        self.send("prima", photo=self.small_jpg, vision=[NOT_ASSESSABLE])
        self.send("seconda", photo=self.small_png, vision=[NOT_ASSESSABLE])
        self.assertEqual(self.supervisor, [])
        self.send("no")
        self.assertEqual(self.supervisor, [None])

    def test_broken_vision_answer_goes_on_without_photo(self):
        """TEST photography: an unreadable vision answer goes on without the photo instead of crashing."""
        self.send("ecco", photo=self.small_png, vision=["risposta troncata {\"lesion"])
        self.assertIn("Si procede senza foto", self.messages_from("Fotografia")[0])
        self.assertIsNone(self.supervisor[0])

    def test_answer_with_think_block_is_read(self):
        """TEST photography: a "thinking" model answer (<think> block before the JSON) is read correctly."""
        self.send("ecco", photo=self.small_png, vision=["<think>osservo la foto</think>```json\n"
                                                        '{"lesion_type": "ustione", "description": "Arrossamento."}\n```'])
        self.assertEqual(self.supervisor[0].injury_type, "ustione")


if __name__ == "__main__":
    unittest.main()
