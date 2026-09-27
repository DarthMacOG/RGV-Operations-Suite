# RGV Operations Suite

A Windows desktop application for applying a reusable watermark to photos and
videos from RGV camera workflows.

## Version 1.2.1 features

- Batch queue for JPG, PNG, WEBP, MP4, MOV, AVI, and MKV files
- Built-in RGV watermark preset plus a custom-logo option
- Automatic placement: bottom-left for photos and top-right for videos
- Adjustable watermark size, opacity, and margin
- Non-destructive exports with collision-safe filenames
- Image exports powered by Pillow
- Video exports powered by FFmpeg
- Compatibility-focused H.264/AAC MP4 output for every source video format
- Remembered logo, output folder, and watermark preferences
- Warning before reprocessing an existing `_RGV` export
- Official RGV branding and application icon
- Dark Windows interface with progress and completion feedback

## Run from source

Python 3.11 or newer is recommended.

```powershell
python -m pip install -r requirements.txt
python app.py
```

Video export also requires FFmpeg when running from source. The packaged Windows
application includes its own compatible FFmpeg engine.

## Build the Windows application

```powershell
python -m pip install -r requirements-build.txt
.\build.ps1
```

The standalone application will be created in `dist`. GitHub Releases contains
the tested operator-ready builds.

## Using the app

1. Add one or more photos or videos.
2. Choose the RGV preset or select a custom transparent logo.
3. Adjust size, opacity, and margin.
4. Choose an output folder.
5. Select **Export Watermarked Media**.

Original media is never modified. Exports use `_RGV` in the filename, and
existing exports are never overwritten.
