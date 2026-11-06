"""Where finished PDFs are kept: a local folder, or a Cloud Storage bucket.

Both lay files out the same way, one folder per project (named after the
course) and one meaningfully named PDF per course:

    <root>/cot5407-algorithms/01-cot5407-introduction-to-asymptotic-analysis.pdf
"""
import os
import shutil

from aicc_demo.export import slugify


def pdf_name(position: int, course_title: str) -> str:
    """`01-course-title.pdf`: the number keeps files in the Canvas module order."""
    return f"{position:02d}-{slugify(course_title)}.pdf"


class LocalPdfStore:
    def __init__(self, root: str):
        self.root = root

    def location(self, folder: str) -> str:
        return os.path.join(self.root, folder) + os.sep

    def save(self, local_pdf: str, folder: str, name: str) -> str:
        target_dir = os.path.join(self.root, folder)
        os.makedirs(target_dir, exist_ok=True)
        target = os.path.join(target_dir, name)
        if os.path.abspath(local_pdf) != os.path.abspath(target):
            shutil.move(local_pdf, target)
        return target

    def exists(self, ref: str | None) -> bool:
        return bool(ref) and os.path.exists(ref)

    def size(self, ref: str) -> int:
        return os.path.getsize(ref)

    def read(self, ref: str) -> bytes:
        with open(ref, "rb") as f:
            return f.read()

    def delete(self, ref: str) -> None:
        if ref and os.path.exists(ref):
            os.remove(ref)


class GcsPdfStore:
    def __init__(self, bucket: str, client=None):
        from google.cloud import storage

        self.bucket_name = bucket
        self.bucket = (client or storage.Client()).bucket(bucket)

    def location(self, folder: str) -> str:
        return f"gs://{self.bucket_name}/{folder}/"

    def _blob(self, ref: str):
        prefix = f"gs://{self.bucket_name}/"
        if not ref.startswith(prefix):
            raise ValueError(f"Not in bucket {self.bucket_name}: {ref}")
        return self.bucket.blob(ref[len(prefix):])

    def save(self, local_pdf: str, folder: str, name: str) -> str:
        blob = self.bucket.blob(f"{folder}/{name}")
        blob.upload_from_filename(local_pdf, content_type="application/pdf")
        return f"gs://{self.bucket_name}/{folder}/{name}"

    def exists(self, ref: str | None) -> bool:
        return bool(ref) and self._blob(ref).exists()

    def size(self, ref: str) -> int:
        blob = self._blob(ref)
        blob.reload()
        return blob.size or 0

    def read(self, ref: str) -> bytes:
        return self._blob(ref).download_as_bytes()

    def delete(self, ref: str) -> None:
        blob = self._blob(ref)
        if blob.exists():
            blob.delete()
