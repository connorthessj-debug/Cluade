"""
Driver's license reader using OCR and face extraction.

Captures an image of a driver's license held up to the camera, extracts:
- Full name
- Date of birth
- License number
- Address
- Face photo from the license

Uses Tesseract OCR for text and face_recognition for the photo.

Supports common US driver's license layouts. May need tuning for
specific state formats.
"""

import re
from dataclasses import dataclass

import cv2
import numpy as np

try:
    import pytesseract
    HAS_TESSERACT = True
except ImportError:
    HAS_TESSERACT = False

try:
    import face_recognition
    HAS_FACE_RECOGNITION = True
except ImportError:
    HAS_FACE_RECOGNITION = False


@dataclass
class LicenseData:
    """Parsed data from a driver's license."""
    first_name: str = ""
    last_name: str = ""
    full_name: str = ""
    license_number: str = ""
    date_of_birth: str = ""
    address: str = ""
    state: str = ""
    face_encoding: object = None  # 128-d numpy array if face found
    face_image: object = None     # Cropped face as numpy array
    raw_text: str = ""            # Full OCR output for debugging
    confidence: float = 0.0       # Overall parse confidence

    @property
    def is_valid(self) -> bool:
        """Minimum fields needed for a badge."""
        return bool(self.full_name or (self.first_name and self.last_name))

    def to_dict(self) -> dict:
        return {
            "first_name": self.first_name,
            "last_name": self.last_name,
            "full_name": self.full_name or f"{self.first_name} {self.last_name}".strip(),
            "license_number": self.license_number,
            "date_of_birth": self.date_of_birth,
            "address": self.address,
            "state": self.state,
        }


def preprocess_image(image: np.ndarray) -> np.ndarray:
    """Preprocess a license image for better OCR accuracy.

    Applies grayscale conversion, adaptive thresholding, and denoising.
    """
    # Convert to grayscale
    if len(image.shape) == 3:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    else:
        gray = image.copy()

    # Denoise
    gray = cv2.fastNlMeansDenoising(gray, h=10)

    # Increase contrast with CLAHE
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray = clahe.apply(gray)

    # Adaptive thresholding for text
    binary = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY, 11, 2
    )

    return binary


def detect_license_region(image: np.ndarray) -> np.ndarray:
    """Try to detect and crop the license card region from the frame.

    Looks for a rectangular card shape. Returns the cropped region
    or the original image if no card is detected.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY) if len(image.shape) == 3 else image
    blurred = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blurred, 50, 150)

    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # Look for a large rectangular contour (the license card)
    img_area = image.shape[0] * image.shape[1]
    for contour in sorted(contours, key=cv2.contourArea, reverse=True):
        area = cv2.contourArea(contour)
        if area < img_area * 0.1:  # Too small
            continue

        # Approximate the contour to a polygon
        peri = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, 0.02 * peri, True)

        # A card should be roughly rectangular (4 corners)
        if len(approx) == 4:
            # Perspective transform to flatten the card
            pts = approx.reshape(4, 2).astype(np.float32)
            rect = _order_points(pts)
            width = int(max(
                np.linalg.norm(rect[0] - rect[1]),
                np.linalg.norm(rect[2] - rect[3]),
            ))
            height = int(max(
                np.linalg.norm(rect[0] - rect[3]),
                np.linalg.norm(rect[1] - rect[2]),
            ))

            if width > 200 and height > 100:
                dst = np.array([
                    [0, 0], [width, 0],
                    [width, height], [0, height],
                ], dtype=np.float32)
                matrix = cv2.getPerspectiveTransform(rect, dst)
                warped = cv2.warpPerspective(image, matrix, (width, height))
                return warped

    return image


def _order_points(pts: np.ndarray) -> np.ndarray:
    """Order 4 points as: top-left, top-right, bottom-right, bottom-left."""
    rect = np.zeros((4, 2), dtype=np.float32)
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]   # Top-left has smallest sum
    rect[2] = pts[np.argmax(s)]   # Bottom-right has largest sum
    d = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(d)]   # Top-right has smallest difference
    rect[3] = pts[np.argmax(d)]   # Bottom-left has largest difference
    return rect


def extract_text(image: np.ndarray) -> str:
    """Run OCR on the image and return the raw text."""
    if not HAS_TESSERACT:
        raise RuntimeError(
            "pytesseract not installed. Install with: "
            "pip install pytesseract && sudo apt install tesseract-ocr"
        )

    processed = preprocess_image(image)

    # Run Tesseract with settings optimized for ID cards
    custom_config = r'--oem 3 --psm 6'
    text = pytesseract.image_to_string(processed, config=custom_config)

    return text


def extract_face_from_license(image: np.ndarray):
    """Extract the face photo from a license image.

    Returns (face_encoding, face_image) or (None, None).
    """
    if not HAS_FACE_RECOGNITION:
        return None, None

    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB) if len(image.shape) == 3 else image

    locations = face_recognition.face_locations(rgb, model="hog")
    if not locations:
        return None, None

    # Use the largest face found (should be the license photo)
    largest = max(locations, key=lambda loc: (loc[2] - loc[0]) * (loc[1] - loc[3]))
    top, right, bottom, left = largest

    encodings = face_recognition.face_encodings(rgb, [largest])
    encoding = encodings[0] if encodings else None

    face_img = image[top:bottom, left:right]

    return encoding, face_img


def parse_license_text(text: str) -> dict:
    """Parse OCR text from a US driver's license into structured fields.

    US licenses vary by state but commonly contain labeled fields like:
    - LN / LAST NAME / FN / FIRST NAME
    - DL / LICENSE NO
    - DOB / DATE OF BIRTH
    - Address lines

    This parser uses regex patterns to find these fields.
    """
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    result = {
        "first_name": "",
        "last_name": "",
        "full_name": "",
        "license_number": "",
        "date_of_birth": "",
        "address": "",
        "state": "",
    }

    full_text = " ".join(lines).upper()

    # --- Last Name ---
    ln_patterns = [
        r'(?:LN|LAST\s*NAME|SURNAME)[:\s]+([A-Z][A-Z\s\-\']+)',
        r'(?:^|\n)([A-Z][A-Z\-\']+)\s*$',  # Standalone uppercase word on a line
    ]
    for pattern in ln_patterns:
        match = re.search(pattern, full_text)
        if match:
            result["last_name"] = match.group(1).strip().title()
            break

    # --- First Name ---
    fn_patterns = [
        r'(?:FN|FIRST\s*NAME|GIVEN\s*NAME)[:\s]+([A-Z][A-Z\s\-\']+)',
    ]
    for pattern in fn_patterns:
        match = re.search(pattern, full_text)
        if match:
            result["first_name"] = match.group(1).strip().title()
            break

    # --- Full Name (fallback) ---
    name_patterns = [
        r'(?:NAME)[:\s]+([A-Z][A-Z\s\-\',]+)',
    ]
    for pattern in name_patterns:
        match = re.search(pattern, full_text)
        if match:
            result["full_name"] = match.group(1).strip().title()
            break

    if not result["full_name"] and result["first_name"] and result["last_name"]:
        result["full_name"] = f"{result['first_name']} {result['last_name']}"

    # --- License Number ---
    dl_patterns = [
        r'(?:DL|DLN|LICENSE\s*(?:NO|NUM|NUMBER|#))[:\s]*([A-Z0-9\-]+)',
        r'(?:^|\s)([A-Z]\d{6,12})(?:\s|$)',  # Common format: letter + digits
    ]
    for pattern in dl_patterns:
        match = re.search(pattern, full_text)
        if match:
            result["license_number"] = match.group(1).strip()
            break

    # --- Date of Birth ---
    dob_patterns = [
        r'(?:DOB|DATE\s*OF\s*BIRTH|BORN|BD)[:\s]*(\d{1,2}[\-/]\d{1,2}[\-/]\d{2,4})',
        r'(\d{2}/\d{2}/\d{4})',  # MM/DD/YYYY
    ]
    for pattern in dob_patterns:
        match = re.search(pattern, full_text)
        if match:
            result["date_of_birth"] = match.group(1).strip()
            break

    # --- Address ---
    addr_patterns = [
        r'(?:ADDR|ADDRESS)[:\s]+(.+?)(?:(?:DOB|DL|CLASS|EXP|ISS)|$)',
        r'(\d+\s+[A-Z][A-Z\s]+(?:ST|AVE|BLVD|DR|RD|LN|CT|WAY|PL)\.?)',
    ]
    for pattern in addr_patterns:
        match = re.search(pattern, full_text)
        if match:
            result["address"] = match.group(1).strip().title()
            break

    # --- State ---
    # Look for 2-letter state abbreviation
    state_match = re.search(
        r'\b(AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|'
        r'MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|OH|OK|OR|PA|RI|SC|SD|'
        r'TN|TX|UT|VT|VA|WA|WV|WI|WY|DC)\b',
        full_text
    )
    if state_match:
        result["state"] = state_match.group(1)

    return result


def read_license(image: np.ndarray) -> LicenseData:
    """Full pipeline: detect license, OCR text, extract face.

    Args:
        image: BGR image from camera (numpy array).

    Returns:
        LicenseData with all extracted fields.
    """
    # Step 1: Try to detect and crop the card region
    cropped = detect_license_region(image)

    # Step 2: OCR
    raw_text = extract_text(cropped)

    # Step 3: Parse structured fields
    fields = parse_license_text(raw_text)

    # Step 4: Extract face from license photo
    face_encoding, face_image = extract_face_from_license(cropped)

    # Calculate confidence based on how many fields were found
    filled = sum(1 for v in fields.values() if v)
    confidence = filled / len(fields)

    return LicenseData(
        first_name=fields["first_name"],
        last_name=fields["last_name"],
        full_name=fields["full_name"],
        license_number=fields["license_number"],
        date_of_birth=fields["date_of_birth"],
        address=fields["address"],
        state=fields["state"],
        face_encoding=face_encoding,
        face_image=face_image,
        raw_text=raw_text,
        confidence=confidence,
    )


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python license_reader.py <image_path>")
        print("       python license_reader.py --camera")
        sys.exit(1)

    if sys.argv[1] == "--camera":
        cap = cv2.VideoCapture(0)
        print("Hold license up to camera. Press SPACE to capture, Q to quit.")
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            cv2.imshow("License Scanner", frame)
            key = cv2.waitKey(1) & 0xFF
            if key == ord(' '):
                result = read_license(frame)
                print(f"\nOCR Raw Text:\n{result.raw_text}")
                print(f"\nParsed: {result.to_dict()}")
                print(f"Face found: {result.face_encoding is not None}")
                print(f"Confidence: {result.confidence:.0%}")
                print(f"Valid for badge: {result.is_valid}")
            elif key == ord('q'):
                break
        cap.release()
        cv2.destroyAllWindows()
    else:
        image = cv2.imread(sys.argv[1])
        if image is None:
            print(f"Cannot read image: {sys.argv[1]}")
            sys.exit(1)
        result = read_license(image)
        print(f"OCR Raw Text:\n{result.raw_text}")
        print(f"\nParsed: {result.to_dict()}")
        print(f"Face found: {result.face_encoding is not None}")
        print(f"Confidence: {result.confidence:.0%}")
        print(f"Valid for badge: {result.is_valid}")
