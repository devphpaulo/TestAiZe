"""Working draft. Copy, save and attach all render this same model."""

from __future__ import annotations

import uuid

from PIL import Image

from .geometry import Rect
from .render import Annotation, png_bytes, render_capture


class Draft:
    def __init__(self, base: Image.Image, crop: Rect) -> None:
        self.base = base
        self.crop = crop
        self.annotations: list[Annotation] = []
        self.color = "#E10600"
        self.render_revision = 1
        self.command_id = uuid.uuid4().hex
        self.pending: dict | None = None

    def touch(self) -> None:
        self.render_revision += 1
        self.command_id = uuid.uuid4().hex
        self.pending = None

    def set_crop(self, crop: Rect | None) -> None:
        if crop is None:
            return
        self.crop = crop
        self.touch()

    def add(self, note: Annotation) -> None:
        self.annotations.append(note)
        self.touch()

    def undo(self) -> bool:
        if not self.annotations:
            return False
        self.annotations.pop()
        self.touch()
        return True

    def image(self) -> Image.Image:
        return render_capture(self.base, self.crop, self.annotations)

    def png(self) -> bytes:
        return png_bytes(self.image())

    def freeze(self, context: dict) -> dict:
        same = (
            self.pending is not None
            and self.pending["render_revision"] == str(self.render_revision)
            and self.pending["step_id"] == context["step_id"]
            and self.pending["execution_generation"] == context["execution_generation"]
            and self.pending["expected_revision"] == context["result_revision"]
            and self.pending["command_id"] == self.command_id
        )
        if same:
            return self.pending
        self.pending = {
            "command_id": self.command_id,
            "render_revision": str(self.render_revision),
            "png": self.png(),
            "session_id": context["session_id"],
            "case_id": context["case_id"],
            "step_id": context["step_id"],
            "execution_generation": context["execution_generation"],
            "expected_revision": context["result_revision"],
        }
        return self.pending

    def finish_command(self) -> None:
        """A confirmed attach is complete. The next click is a new explicit action."""
        self.command_id = uuid.uuid4().hex
        self.pending = None
