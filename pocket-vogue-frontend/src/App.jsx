import { useState, useEffect, useRef } from "react";
import "./design.css";

const API_BASE = "http://127.0.0.1:8000";

function cleanLabel(str, prefix = "", suffix = "") {
  let s = str || "";
  if (prefix) s = s.replace(prefix, "");
  if (suffix) s = s.replace(suffix, "");
  return s.trim();
}

function formatItem(item) {
  return {
    type: cleanLabel(item.clothing_type, "a photo of "),
    color: cleanLabel(item.color, "", " item of clothing"),
    material: cleanLabel(item.material, "clothing made of "),
  };
}

export default function App() {
  const [screen, setScreen] = useState("wardrobe");
  const [items, setItems] = useState([]);
  const [currentIdx, setCurrentIdx] = useState(0);
  const [animating, setAnimating] = useState(false);
  const [outfit, setOutfit] = useState(null);
  const [outfitAnchor, setOutfitAnchor] = useState(null);
  const [loading, setLoading] = useState(false);
  const [loadingText, setLoadingText] = useState("");
  const [files, setFiles] = useState([]);
  const [uploadStatus, setUploadStatus] = useState("");
  const [toast, setToast] = useState(null);
  const fileInputRef = useRef();

  useEffect(() => {
    fetchWardrobe();
  }, []);

  useEffect(() => {
    if (toast) {
      const t = setTimeout(() => setToast(null), 3500);
      return () => clearTimeout(t);
    }
  }, [toast]);

  async function fetchWardrobe() {
    try {
      const res = await fetch(`${API_BASE}/wardrobe/`);
      const data = await res.json();
      setItems(data.items || []);
      setCurrentIdx(0);
    } catch {
      showToast("Could not connect to backend");
    }
  }

  function showToast(msg) {
    setToast(msg);
  }

  function nextItem() {
    if (animating || items.length < 2) return;
    setAnimating(true);
    setTimeout(() => {
      setCurrentIdx((i) => (i + 1) % items.length);
      setAnimating(false);
    }, 380);
  }

  function prevItem() {
    if (animating || items.length < 2) return;
    setCurrentIdx((i) => (i - 1 + items.length) % items.length);
  }

  async function generateOutfit() {
    if (!items.length) return;
    const item = items[currentIdx];
    setLoading(true);
    setLoadingText("Styling your outfit...");
    setOutfitAnchor(item);
    try {
      const res = await fetch(`${API_BASE}/generate-outfit/${item.id}`);
      if (!res.ok) throw new Error("Generation failed");
      const data = await res.json();
      setOutfit(data);
      setScreen("outfit");
    } catch {
      showToast("Outfit generation failed — try again");
    } finally {
      setLoading(false);
    }
  }

  function onFileSelect(e) {
    const selected = Array.from(e.target.files);
    if (!selected.length) return;
    setFiles((prev) => [...prev, ...selected]);
    setUploadStatus("");
  }

  function removeFile(idx) {
    setFiles((prev) => prev.filter((_, i) => i !== idx));
  }

  async function uploadFiles() {
    if (!files.length) return;
    setLoading(true);
    setLoadingText("Analyzing your items...");
    setUploadStatus("");
    const formData = new FormData();
    files.forEach((f) => formData.append("files", f));
    try {
      const res = await fetch(`${API_BASE}/upload-image/`, {
        method: "POST",
        body: formData,
      });
      if (!res.ok) throw new Error();
      const data = await res.json();
      const count = data.uploaded?.filter((u) => u.status === "success").length || 0;
      setFiles([]);
      setUploadStatus(`${count} item${count !== 1 ? "s" : ""} added`);
      await fetchWardrobe();
      setTimeout(() => {
        setScreen("wardrobe");
        setUploadStatus("");
      }, 1200);
    } catch {
      setUploadStatus("Upload failed — check your backend is running");
    } finally {
      setLoading(false);
    }
  }

  // Carousel: compute position class for each visible item
  function getCarouselPosition(offset) {
    // offset: -2, -1, 0, +1, +2 from center
    if (offset === 0) return "carousel-item pos-center";
    if (offset === -1) return "carousel-item pos-left1";
    if (offset === 1) return "carousel-item pos-right1";
    if (offset === -2) return "carousel-item pos-left2";
    if (offset === 2) return "carousel-item pos-right2";
    return "carousel-item pos-hidden";
  }

  // Get 5 items centered on currentIdx
  const carouselSlots = items.length
    ? [-2, -1, 0, 1, 2].map((offset) => ({
        offset,
        item: items[((currentIdx + offset) % items.length + items.length) % items.length],
      }))
    : [];

  // Drag / swipe handlers
  const dragRef = useRef({ startX: 0, dragging: false });

  function onDragStart(e) {
    dragRef.current.startX = e.clientX || e.touches?.[0]?.clientX || 0;
    dragRef.current.dragging = true;
  }
  function onDragEnd(e) {
    if (!dragRef.current.dragging) return;
    dragRef.current.dragging = false;
    const endX = e.clientX || e.changedTouches?.[0]?.clientX || 0;
    const diff = endX - dragRef.current.startX;
    if (Math.abs(diff) > 50) {
      if (diff > 0) prevItem();
      else nextItem();
    }
  }

  function findOutfitItem(id) {
    return items.find((i) => i.id === id);
  }

  return (
    <>
      {/* Ambient gradient background */}
      <div className="ambient-bg" />

      <div className="app">
        {loading && (
          <div className="loading-overlay">
            <div className="spinner-ring" />
            <p className="loading-label">{loadingText}</p>
          </div>
        )}

        {toast && <div className="toast">{toast}</div>}

        <nav className="nav">
          <span className="nav-logo">Pocket Vogue</span>
          <div className="nav-tabs">
            <button
              className={`nav-tab ${screen === "wardrobe" || screen === "outfit" ? "active" : ""}`}
              onClick={() => setScreen("wardrobe")}
            >
              Wardrobe
            </button>
            <button
              className={`nav-tab ${screen === "upload" ? "active" : ""}`}
              onClick={() => setScreen("upload")}
            >
              Upload
            </button>
          </div>
          <button
            className="nav-add"
            aria-label="Add items"
            onClick={() => setScreen("upload")}
          >
            +
          </button>
        </nav>

        {/* WARDROBE SCREEN */}
        {screen === "wardrobe" && (
          <div className="wardrobe-screen screen-enter" key="wardrobe">
            <div className="wardrobe-header">
              <span className="wardrobe-title">My wardrobe</span>
              <span className="wardrobe-count">
                {items.length} {items.length === 1 ? "item" : "items"}
              </span>
            </div>

            {items.length === 0 ? (
              <div className="empty-wardrobe">
                <div className="empty-icon">👗</div>
                <p className="empty-label">
                  Your wardrobe is empty.<br />Upload some items to get started.
                </p>
                <button className="empty-action" onClick={() => setScreen("upload")}>
                  Add clothing
                </button>
              </div>
            ) : (
              <>
                <div className="carousel-area">
                  <div
                    className="carousel-track"
                    onMouseDown={onDragStart}
                    onMouseUp={onDragEnd}
                    onMouseLeave={() => { dragRef.current.dragging = false; }}
                    onTouchStart={onDragStart}
                    onTouchEnd={onDragEnd}
                  >
                    {carouselSlots.map(({ offset, item }) => {
                      const fmt = formatItem(item);
                      return (
                        <div
                          key={item.id + "-" + offset}
                          className={getCarouselPosition(offset)}
                          onClick={() => {
                            if (offset === 0) generateOutfit();
                            else if (offset < 0) prevItem();
                            else nextItem();
                          }}
                        >
                          {item.image_url ? (
                            <img className="card-image" src={item.image_url} alt={fmt.type} />
                          ) : (
                            <div className="card-image-placeholder">👕</div>
                          )}
                          <div className="card-footer">
                            <p className="card-type">{fmt.type}</p>
                            <p className="card-sub">{fmt.color} · {fmt.material}</p>
                          </div>
                        </div>
                      );
                    })}
                  </div>

                  <div className="carousel-nav">
                    <button className="carousel-arrow" onClick={prevItem} aria-label="Previous item">
                      ←
                    </button>
                    <span className="carousel-pos">
                      {currentIdx + 1} / {items.length}
                    </span>
                    <button className="carousel-arrow" onClick={nextItem} aria-label="Next item">
                      →
                    </button>
                  </div>
                </div>

                <button
                  className="generate-btn"
                  onClick={generateOutfit}
                  disabled={loading}
                >
                  ✦ Generate outfit from this item
                </button>
              </>
            )}
          </div>
        )}

        {/* OUTFIT SCREEN */}
        {screen === "outfit" && outfit && (
          <div className="outfit-screen screen-enter" key="outfit">
            <div className="outfit-inner">
              <button className="back-btn" onClick={() => setScreen("wardrobe")}>
                ← Back
              </button>

              {outfitAnchor && (
                <div className="outfit-anchor">
                  <div className="outfit-anchor-thumb">
                    {outfitAnchor.image_url ? (
                      <img src={outfitAnchor.image_url} alt="anchor" />
                    ) : (
                      "👕"
                    )}
                  </div>
                  <div>
                    <p className="outfit-anchor-eyebrow">Building around</p>
                    <p className="outfit-anchor-name">
                      {formatItem(outfitAnchor).type}
                    </p>
                  </div>
                </div>
              )}

              <p className="outfit-pieces-label">Selected pieces</p>

              <div className="outfit-pieces">
                {(outfit.outfit || []).map((piece, i) => {
                  const matched = findOutfitItem(piece.id);
                  return (
                    <div key={i} className="outfit-piece">
                      <div className="outfit-piece-thumb">
                        {matched?.image_url ? (
                          <img src={matched.image_url} alt={piece.item} />
                        ) : (
                          "👔"
                        )}
                      </div>
                      <div>
                        <p className="outfit-piece-name">
                          {piece.item || (matched && formatItem(matched).type)}
                        </p>
                        <p className="outfit-piece-reason">{piece.reason}</p>
                      </div>
                    </div>
                  );
                })}
              </div>

              {outfit.overall_description && (
                <div className="outfit-vibe">
                  <p className="outfit-vibe-label">The vibe</p>
                  <p className="outfit-vibe-text">{outfit.overall_description}</p>
                </div>
              )}
            </div>
          </div>
        )}

        {/* UPLOAD SCREEN */}
        {screen === "upload" && (
          <div className="upload-screen screen-enter" key="upload">
            <div>
              <p className="upload-title">Add items</p>
              <p className="upload-sub">
                Upload one or more clothing photos. The AI will classify each item automatically.
              </p>
            </div>

            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              multiple
              onChange={onFileSelect}
            />

            <div
              className="upload-dropzone"
              onClick={() => fileInputRef.current.click()}
            >
              <div className="upload-dropzone-icon">☁</div>
              <p className="upload-dropzone-label">Tap to browse photos</p>
              <p className="upload-dropzone-hint">JPG, PNG, WEBP — multiple files supported</p>
            </div>

            {files.length > 0 && (
              <div className="upload-grid">
                {files.map((f, i) => (
                  <div key={i} className="upload-thumb">
                    <img src={URL.createObjectURL(f)} alt={f.name} />
                    <button
                      className="upload-thumb-remove"
                      onClick={() => removeFile(i)}
                      aria-label="Remove"
                    >
                      ×
                    </button>
                  </div>
                ))}
              </div>
            )}

            {uploadStatus && (
              <p
                className={`upload-status ${
                  uploadStatus.includes("failed") ? "error" : "success"
                }`}
              >
                {uploadStatus}
              </p>
            )}

            <button
              className="upload-submit-btn"
              onClick={uploadFiles}
              disabled={!files.length || loading}
            >
              {files.length > 0
                ? `Analyze ${files.length} item${files.length > 1 ? "s" : ""}`
                : "Select photos first"}
            </button>
          </div>
        )}
      </div>
    </>
  );
}
