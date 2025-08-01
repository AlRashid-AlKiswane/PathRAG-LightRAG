"""
upload_route.py

This module defines an API route for uploading multiple files into organized directories.
It validates allowed file types, sanitizes directory names, and stores uploaded files 
in a configured document location. 

Each uploaded file is assigned a unique filename to prevent overwriting, and results 
are returned per file with status and metadata (size, path, etc.).

Endpoint:
    POST /api/v1/files/multi/

Query Parameters:
    - dir_name (str, optional): Custom directory name under the upload base path to store files.

Body:
    - files (List[UploadFile]): List of one or more files to upload via multipart/form-data.

Returns:
    JSONResponse: Dictionary with:
        - success_count (int): Number of files uploaded successfully.
        - failed_count (int): Number of files that failed to upload.
        - details (List[Dict]): Metadata and error info for each file.

Behavior:
    - Allowed file extensions are enforced (via `app_settings.FILE_TYPES`).
    - Directories are automatically created if not present.
    - Each file is saved with a generated unique name using `generate_unique_filename`.
    - Logs are written for each stage: validation, saving, and errors.

Raises:
    - HTTPException 400: If no files are provided or upload fails due to bad input.
    - Any internal I/O errors are captured and logged per file without failing the entire batch.

Dependencies:
    - FastAPI
    - Python standard libraries: os, shutil, pathlib
    - Custom project modules: `generate_unique_filename`, `get_size`, settings, logging

Author:
    ALRashid AlKiswane
"""

import os
import sys
import shutil
from pathlib import Path
import logging
from typing import List, Dict, Any
from fastapi import APIRouter, UploadFile, File, HTTPException, status
from fastapi.responses import JSONResponse

# Set up project base directory
try:
    MAIN_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    sys.path.append(MAIN_DIR)
except (ImportError, OSError) as e:
    logging.error("Failed to set up main directory path: %s", e)
    sys.exit(1)

# pylint: disable=wrong-import-position
from src.infra import setup_logging
from src.helpers import get_settings, Settings
from src.controllers import generate_unique_filename
from src.utils import get_size

# Initialize logger and settings
logger = setup_logging(name="UPLOAD-FILE(s)")
app_settings: Settings = get_settings()


upload_route = APIRouter(
    prefix="/api/v1/files",
    tags=["File Uploads"],
    responses={404: {"description": "Not found"}}
)

UPLOAD_DIR = app_settings.DOC_LOCATION_STORE
ALLOWED_EXTENSIONS = app_settings.FILE_TYPES


@upload_route.post(
    "/multi/",
    response_model=Dict[str, Any],
    status_code=status.HTTP_207_MULTI_STATUS,
    summary="Upload multiple files",
    response_description="Returns upload results for each file"
)
async def upload_multiple_files(
    files: List[UploadFile] = File(..., description="List of files to upload"),
    dir_name: str = None
) -> JSONResponse:
    """
    Handle multiple file uploads with validation and organization.

    Args:
        files: List of files to be uploaded
        dir_name: Optional custom directory name for storage. If not provided,
                  will create directory based on first file's name.

    Returns:
        JSONResponse: Detailed results including:
            - success_count: Number of successfully uploaded files
            - failed_count: Number of failed uploads
            - details: List of upload results for each file

    Raises:
        HTTPException: 400 if no files provided or invalid directory name
    """
    logger.info("Starting multiple file upload process")
    
    if not files:
        logger.error("No files provided in upload request")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one file must be provided"
        )

    results = []
    first_file_dir = None

    for file in files:
        try:
            logger.debug(f"Processing file: {file.filename}")

            # Validate file extension
            file_ext = Path(file.filename).suffix.lower()
            if file_ext not in ALLOWED_EXTENSIONS:
                logger.warning(f"Invalid file extension {file_ext} for {file.filename}")
                raise ValueError(f"File type {file_ext} not allowed")

            # Determine directory name
            current_dir_name = dir_name or Path(file.filename).stem
            sanitized_dir = "".join(
                c if c.isalnum() or c in ('-', '_') else '_' 
                for c in current_dir_name
            )[:30]
            
            save_dir = os.path.join(UPLOAD_DIR, sanitized_dir)
            logger.debug(f"Preparing to save to directory: {save_dir}")

            # Create directory if needed
            os.makedirs(save_dir, exist_ok=True)

            # Generate unique filename
            unique_filename = generate_unique_filename(file.filename)
            save_path = os.path.join(save_dir, unique_filename)
            logger.debug(f"Generated save path: {save_path}")

            # Save file
            with open(save_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            logger.info(f"Successfully saved file: {save_path}")

            # Record successful upload
            results.append({
                "original_name": file.filename,
                "saved_path": save_path,
                "directory": sanitized_dir,
                "size": get_size(save_path),
                "status": "success"
            })

        except Exception as e:
            logger.error(f"Failed to process {file.filename}: {str(e)}", exc_info=True)
            results.append({
                "original_name": file.filename,
                "error": str(e),
                "status": "failed"
            })

    # Prepare response
    success_count = len([r for r in results if r.get("status") == "success"])
    failed_count = len(results) - success_count

    logger.info(
        f"Upload process completed. Success: {success_count}, Failed: {failed_count}"
    )

    return JSONResponse({
        "success_count": success_count,
        "failed_count": failed_count,
        "details": results
    })
