(() => {
  "use strict";

  const ALLOWED_EXT = ["jpg", "jpeg", "png", "webp"];
  const ALLOWED_MIME = ["image/jpeg", "image/png", "image/webp"];
  const MAX_UPLOAD_MB = Number(document.body.dataset.maxUploadMb) || 25;

  // --- Element references ---
  const dropzone = document.getElementById("dropzone");
  const fileInput = document.getElementById("file-input");
  const browseBtn = document.getElementById("browse-btn");
  const fileMetaCard = document.getElementById("file-meta-card");
  const originalPreview = document.getElementById("original-preview");
  const metaFilename = document.getElementById("meta-filename");
  const metaFiletype = document.getElementById("meta-filetype");
  const metaDimensions = document.getElementById("meta-dimensions");
  const metaFilesize = document.getElementById("meta-filesize");
  const removeFileBtn = document.getElementById("remove-file-btn");
  const errorBanner = document.getElementById("error-banner");
  const controls = document.getElementById("controls");

  const targetChips = document.getElementById("target-size-chips");
  const customSizeRow = document.getElementById("custom-size-row");
  const customSizeValue = document.getElementById("custom-size-value");
  const customSizeUnit = document.getElementById("custom-size-unit");
  const modeChips = document.getElementById("mode-chips");

  const maxWidthInput = document.getElementById("max-width");
  const maxHeightInput = document.getElementById("max-height");
  const outputFormatSelect = document.getElementById("output-format");
  const jpegQualityInput = document.getElementById("jpeg-quality");

  const compressBtn = document.getElementById("compress-btn");
  const compressBtnLabel = document.getElementById("compress-btn-label");
  const compressSpinner = document.getElementById("compress-spinner");

  const resultPanel = document.getElementById("result-panel");
  const resultOriginalImg = document.getElementById("result-original-img");
  const resultCompressedImg = document.getElementById("result-compressed-img");
  const resultOriginalSize = document.getElementById("result-original-size");
  const resultCompressedSize = document.getElementById("result-compressed-size");
  const resultOriginalDims = document.getElementById("result-original-dims");
  const resultCompressedDims = document.getElementById("result-compressed-dims");
  const squeezeFill = document.getElementById("squeeze-fill");
  const squeezePercent = document.getElementById("squeeze-percent");
  const resultWarning = document.getElementById("result-warning");
  const downloadBtn = document.getElementById("download-btn");
  const compressAnotherBtn = document.getElementById("compress-another-btn");

  // --- State ---
  let selectedFile = null;
  let selectedTargetKey = null; // preset key or 'custom'
  let selectedMode = "balanced";
  let objectUrl = null;
  let isSubmitting = false;

  function showError(message) {
    errorBanner.textContent = message;
    errorBanner.hidden = false;
  }
  function clearError() {
    errorBanner.hidden = true;
    errorBanner.textContent = "";
  }

  function humanSize(bytes) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  }

  function extOf(filename) {
    const parts = filename.split(".");
    return parts.length > 1 ? parts.pop().toLowerCase() : "";
  }

  // --- File selection & client-side validation ---
  function validateFileClientSide(file) {
    const ext = extOf(file.name);
    if (!ALLOWED_EXT.includes(ext)) {
      return `Unsupported file format '.${ext || "?"}'. Please upload a JPG, PNG, or WEBP image.`;
    }
    if (file.type && !ALLOWED_MIME.includes(file.type)) {
      return "This file doesn't look like a supported image type (JPG, PNG, or WEBP).";
    }
    if (file.size <= 0) {
      return "The selected file is empty.";
    }
    if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
      return `File is too large. Maximum upload size is ${MAX_UPLOAD_MB} MB.`;
    }
    return null;
  }

  function handleFileSelected(file) {
    clearError();
    const clientError = validateFileClientSide(file);
    if (clientError) {
      showError(clientError);
      return;
    }

    selectedFile = file;

    if (objectUrl) URL.revokeObjectURL(objectUrl);
    objectUrl = URL.createObjectURL(file);
    originalPreview.src = objectUrl;

    const img = new Image();
    img.onload = () => {
      metaDimensions.textContent = `${img.naturalWidth} × ${img.naturalHeight}`;
      validateTargetAgainstOriginal();
    };
    img.onerror = () => {
      showError("The uploaded file is not a valid image, or the image data is corrupted.");
      resetSelection();
    };
    img.src = objectUrl;

    metaFilename.textContent = file.name;
    metaFiletype.textContent = (file.type || `image/${extOf(file.name)}`).toUpperCase();
    metaFilesize.textContent = humanSize(file.size);

    fileMetaCard.hidden = false;
    controls.hidden = false;
    resultPanel.hidden = true;
  }

  function resetSelection() {
    selectedFile = null;
    fileInput.value = "";
    fileMetaCard.hidden = true;
    controls.hidden = true;
    resultPanel.hidden = true;
    clearError();
    if (objectUrl) {
      URL.revokeObjectURL(objectUrl);
      objectUrl = null;
    }
  }

  dropzone.addEventListener("click", () => fileInput.click());
  dropzone.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      fileInput.click();
    }
  });
  browseBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    fileInput.click();
  });
  fileInput.addEventListener("change", () => {
    if (fileInput.files && fileInput.files[0]) {
      handleFileSelected(fileInput.files[0]);
    }
  });
  removeFileBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    resetSelection();
  });

  ["dragenter", "dragover"].forEach((evt) => {
    dropzone.addEventListener(evt, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropzone.classList.add("drag-active");
    });
  });
  ["dragleave", "drop"].forEach((evt) => {
    dropzone.addEventListener(evt, (e) => {
      e.preventDefault();
      e.stopPropagation();
      dropzone.classList.remove("drag-active");
    });
  });
  dropzone.addEventListener("drop", (e) => {
    const files = e.dataTransfer.files;
    if (files && files[0]) handleFileSelected(files[0]);
  });

  // --- Target size chips ---
  targetChips.addEventListener("click", (e) => {
    const chip = e.target.closest(".chip");
    if (!chip) return;
    [...targetChips.children].forEach((c) => c.classList.remove("chip-active"));
    chip.classList.add("chip-active");
    selectedTargetKey = chip.dataset.target;
    customSizeRow.hidden = selectedTargetKey !== "custom";
    clearError();
    validateTargetAgainstOriginal();
  });

  // --- Mode chips ---
  modeChips.addEventListener("click", (e) => {
    const chip = e.target.closest(".chip");
    if (!chip) return;
    [...modeChips.children].forEach((c) => c.classList.remove("chip-active"));
    chip.classList.add("chip-active");
    selectedMode = chip.dataset.mode;
  });

  function currentTargetBytes() {
    const presets = { "100kb": 100 * 1024, "200kb": 200 * 1024, "300kb": 300 * 1024, "500kb": 500 * 1024, "1mb": 1024 * 1024 };
    if (selectedTargetKey && selectedTargetKey !== "custom") {
      return presets[selectedTargetKey] || null;
    }
    if (selectedTargetKey === "custom") {
      const val = parseFloat(customSizeValue.value);
      if (!val || val <= 0) return null;
      return customSizeUnit.value === "mb" ? val * 1024 * 1024 : val * 1024;
    }
    return null;
  }

  function validateTargetAgainstOriginal() {
    if (!selectedFile) return true;
    const target = currentTargetBytes();
    if (target && target >= selectedFile.size) {
      showError("Target size is already larger than (or equal to) the original file. Choose a smaller target size.");
      return false;
    }
    clearError();
    return true;
  }

  // --- Submit ---
  compressBtn.addEventListener("click", async () => {
    if (isSubmitting) return;
    clearError();

    if (!selectedFile) {
      showError("Please select an image first.");
      return;
    }
    if (!selectedTargetKey) {
      showError("Please choose a target size.");
      return;
    }
    if (selectedTargetKey === "custom") {
      const val = parseFloat(customSizeValue.value);
      if (!val || val <= 0) {
        showError("Please enter a valid custom target size.");
        return;
      }
    }
    if (!validateTargetAgainstOriginal()) return;

    const formData = new FormData();
    formData.append("image", selectedFile);
    formData.append("target_size", selectedTargetKey === "custom" ? customSizeValue.value : selectedTargetKey);
    if (selectedTargetKey === "custom") formData.append("target_unit", customSizeUnit.value);
    formData.append("mode", selectedMode);
    if (outputFormatSelect.value !== "auto") formData.append("output_format", outputFormatSelect.value);
    if (maxWidthInput.value) formData.append("max_width", maxWidthInput.value);
    if (maxHeightInput.value) formData.append("max_height", maxHeightInput.value);
    if (jpegQualityInput.value) formData.append("quality", jpegQualityInput.value);

    setSubmitting(true);
    try {
      const res = await fetch("/compress", { method: "POST", body: formData });
      let payload;
      try {
        payload = await res.json();
      } catch {
        showError("The server returned an unexpected response. Please try again.");
        return;
      }
      if (!res.ok || !payload.success) {
        showError(payload.error || "Compression failed. Please try again.");
        return;
      }
      renderResult(payload);
    } catch (err) {
      showError("Could not reach the server. Check your connection and try again.");
    } finally {
      setSubmitting(false);
    }
  });

  function setSubmitting(state) {
    isSubmitting = state;
    compressBtn.disabled = state;
    compressSpinner.hidden = !state;
    compressBtnLabel.textContent = state ? "Compressing…" : "Compress image";
  }

  function renderResult(payload) {
    resultOriginalImg.src = objectUrl;
    resultCompressedImg.src = payload.download_url + `?t=${Date.now()}`;

    resultOriginalSize.textContent = payload.original_size_readable;
    resultCompressedSize.textContent = payload.compressed_size_readable;
    resultOriginalDims.textContent = `${payload.original_dimensions.width} × ${payload.original_dimensions.height}`;
    resultCompressedDims.textContent = `${payload.new_dimensions.width} × ${payload.new_dimensions.height}`;

    downloadBtn.href = payload.download_url;
    downloadBtn.setAttribute("download", `compressed_${payload.original_filename}`);

    if (payload.warning) {
      resultWarning.textContent = payload.warning;
      resultWarning.hidden = false;
    } else {
      resultWarning.hidden = true;
    }

    resultPanel.hidden = false;
    resultPanel.scrollIntoView({ behavior: "smooth", block: "start" });

    squeezeFill.style.width = "0%";
    squeezePercent.textContent = "0%";
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        const pct = Math.max(0, Math.min(100, payload.reduction_percent));
        squeezeFill.style.width = `${pct}%`;
        squeezePercent.textContent = `${pct}%`;
      });
    });
  }

  compressAnotherBtn.addEventListener("click", () => {
    resetSelection();
    dropzone.scrollIntoView({ behavior: "smooth", block: "start" });
  });
})();
