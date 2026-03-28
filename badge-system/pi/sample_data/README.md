# Sample Data for Training

This directory contains tools to generate synthetic face data for testing
the badge recognition system **before** real employee photos are available.

## Quick Start

```bash
cd badge-system/pi/sample_data

# Generate synthetic database using Olivetti faces (small, no download):
python generate_synthetic.py --source olivetti --count 10 --output ../known_faces.pkl

# Or using LFW dataset (larger, more realistic, downloads ~200MB):
python generate_synthetic.py --source lfw --count 20 --output ../known_faces.pkl

# Or from your own local photos:
python generate_synthetic.py --source local --local-dir ./my_faces/ --output ../known_faces.pkl
```

## Switching to Real Data

When real employee photos become available:

1. Delete the synthetic database: `rm ../known_faces.pkl`
2. Enroll each person using the enrollment script:
   ```bash
   cd badge-system/pi
   python enroll.py --id EMP-0001 --name "Jane Doe" --dept "Engineering" --photos /path/to/jane/photos/
   ```
3. The database format is identical — no code changes needed.

## Local Photos Directory Structure

If using `--source local`, organize photos like this:

```
my_faces/
├── person1/
│   ├── front.jpg
│   ├── angle1.jpg
│   └── angle2.jpg
├── person2/
│   ├── photo1.jpg
│   └── photo2.jpg
```

Multiple photos per person (different angles, lighting) improve accuracy.
