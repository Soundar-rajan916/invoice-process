import React, { useState, useRef, useEffect, useCallback } from "react";
import {
  ZoomIn,
  ZoomOut,
  RotateCw,
  Maximize2,
  Maximize,
  ChevronLeft,
  ChevronRight,
  ArrowLeftRight,
  Layers,
  FileText,
  Sun,
  Moon,
  PanelLeftClose,
  PanelLeftOpen,
  X,
} from "lucide-react";

export interface DocumentPage {
  page_number: number;
  url: string;
}

interface DocumentViewerProps {
  pages: DocumentPage[];
  activePage: number;
  onPageChange: (page: number) => void;
  wideMode?: boolean;
  onToggleWideMode?: () => void;
  filename?: string | null;
  className?: string;
}

export function DocumentViewer({
  pages,
  activePage,
  onPageChange,
  wideMode = false,
  onToggleWideMode,
  filename,
  className = "",
}: DocumentViewerProps) {
  const [scale, setScale] = useState(0.9);
  const [rotation, setRotation] = useState(0);
  const [pan, setPan] = useState({ x: 0, y: 0 });
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const [canvasTheme, setCanvasTheme] = useState<"desk" | "dark">("desk");
  const [showThumbnails, setShowThumbnails] = useState(false);
  const [isFullscreen, setIsFullscreen] = useState(false);

  const containerRef = useRef<HTMLDivElement>(null);
  const imageRef = useRef<HTMLImageElement>(null);

  const totalPages = Math.max(pages.length, 1);
  const currentPageObj =
    pages.find((p) => p.page_number === activePage) || pages[0];
  const currentImageUrl = currentPageObj?.url;

  // Reset pan and scale when changing page
  useEffect(() => {
    setPan({ x: 0, y: 0 });
    setScale(0.9);
  }, [activePage]);

  // Fit to page handler
  const handleFitPage = useCallback(() => {
    if (!containerRef.current || !imageRef.current) {
      setScale(1);
      setPan({ x: 0, y: 0 });
      return;
    }
    const container = containerRef.current.getBoundingClientRect();
    const naturalW = imageRef.current.naturalWidth || 800;
    const naturalH = imageRef.current.naturalHeight || 1100;

    // Account for rotation
    const isSideways = rotation % 180 !== 0;
    const effectiveW = isSideways ? naturalH : naturalW;
    const effectiveH = isSideways ? naturalW : naturalH;

    const availableW = container.width - 48; // padding
    const availableH = container.height - 48;

    const scaleW = availableW / effectiveW;
    const scaleH = availableH / effectiveH;
    const newScale = Math.min(scaleW, scaleH, 1.4);

    setScale(Math.max(0.3, Math.round(newScale * 100) / 100));
    setPan({ x: 0, y: 0 });
  }, [rotation]);

  // Fit to width handler
  const handleFitWidth = useCallback(() => {
    if (!containerRef.current || !imageRef.current) {
      setScale(1.2);
      setPan({ x: 0, y: 0 });
      return;
    }
    const container = containerRef.current.getBoundingClientRect();
    const naturalW = imageRef.current.naturalWidth || 800;
    const naturalH = imageRef.current.naturalHeight || 1100;

    const isSideways = rotation % 180 !== 0;
    const effectiveW = isSideways ? naturalH : naturalW;

    const availableW = container.width - 64; // padding
    const newScale = availableW / effectiveW;

    setScale(Math.max(0.4, Math.round(newScale * 100) / 100));
    setPan({ x: 0, y: 0 });
  }, [rotation]);

  // Handle image load: default to 90% zoom
  const onImageLoad = () => {
    setScale(0.9);
    setPan({ x: 0, y: 0 });
  };

  // Zoom helpers
  const zoomIn = () => setScale((s) => Math.min(3.5, +(s + 0.2).toFixed(2)));
  const zoomOut = () => setScale((s) => Math.max(0.3, +(s - 0.2).toFixed(2)));
  const rotateClockwise = () => setRotation((r) => (r + 90) % 360);
  const resetView = () => {
    setScale(0.9);
    setRotation(0);
    setPan({ x: 0, y: 0 });
  };

  // Mouse pan handlers
  const handleMouseDown = (e: React.MouseEvent) => {
    if (e.button !== 0) return;
    setIsDragging(true);
    setDragStart({ x: e.clientX - pan.x, y: e.clientY - pan.y });
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!isDragging) return;
    setPan({
      x: e.clientX - dragStart.x,
      y: e.clientY - dragStart.y,
    });
  };

  const handleMouseUp = () => setIsDragging(false);

  // Wheel zoom handler
  const handleWheel = (e: React.WheelEvent) => {
    if (e.ctrlKey || e.metaKey) {
      e.preventDefault();
      const zoomFactor = e.deltaY < 0 ? 0.15 : -0.15;
      setScale((s) => Math.min(3.5, Math.max(0.3, +(s + zoomFactor).toFixed(2))));
    }
  };

  // Double-click toggles 90% vs Fit Width
  const handleDoubleClick = () => {
    if (scale !== 0.9) {
      setScale(0.9);
      setPan({ x: 0, y: 0 });
    } else {
      handleFitWidth();
    }
  };

  // Keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (
        target.tagName === "INPUT" ||
        target.tagName === "TEXTAREA" ||
        target.isContentEditable
      ) {
        return;
      }

      if (e.key === "Escape" && isFullscreen) {
        setIsFullscreen(false);
      } else if (e.key === "+" || e.key === "=") {
        zoomIn();
      } else if (e.key === "-") {
        zoomOut();
      } else if (e.key === "0") {
        handleFitPage();
      } else if (e.key.toLowerCase() === "w") {
        handleFitWidth();
      } else if (e.key.toLowerCase() === "r" && !e.ctrlKey && !e.metaKey) {
        rotateClockwise();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isFullscreen, handleFitPage, handleFitWidth]);

  const isDark = canvasTheme === "dark";

  return (
    <div
      className={`flex flex-col h-full min-h-0 select-none overflow-hidden transition-colors ${className}`}
      style={{
        backgroundColor: isDark ? "var(--ink)" : "var(--bg-inset)",
        borderColor: "var(--border)",
      }}
    >
      {/* 1. Header Toolbar */}
      <div
        className="h-12 shrink-0 px-4 flex items-center justify-between border-b text-xs transition-colors z-10"
        style={{
          backgroundColor: isDark ? "#202022" : "var(--bg-inset)",
          borderColor: isDark ? "rgba(255, 255, 255, 0.08)" : "var(--border)",
          color: isDark ? "#E5E5E7" : "var(--text)",
        }}
      >
        {/* Left: Page Navigator */}
        <div className="flex items-center space-x-1.5">
          <button
            type="button"
            onClick={() => onPageChange(Math.max(1, activePage - 1))}
            disabled={activePage <= 1}
            className="w-7 h-7 flex items-center justify-center rounded-btn border transition-colors cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed shadow-2xs"
            style={{
              backgroundColor: isDark ? "#292929" : "var(--bg-card)",
              borderColor: isDark ? "rgba(255, 255, 255, 0.12)" : "var(--border)",
              color: isDark ? "#FFFFFF" : "var(--text)",
            }}
            title="Previous page"
          >
            <ChevronLeft className="h-4 w-4" />
          </button>

          <span
            className="px-2.5 py-1 rounded-btn font-mono text-[11px] font-semibold border shadow-2xs"
            style={{
              backgroundColor: isDark ? "#292929" : "var(--bg-card)",
              borderColor: isDark ? "rgba(255, 255, 255, 0.12)" : "var(--border)",
              color: isDark ? "#FFFFFF" : "var(--text)",
            }}
          >
            {activePage} / {totalPages}
          </span>

          <button
            type="button"
            onClick={() => onPageChange(Math.min(totalPages, activePage + 1))}
            disabled={activePage >= totalPages}
            className="w-7 h-7 flex items-center justify-center rounded-btn border transition-colors cursor-pointer disabled:opacity-30 disabled:cursor-not-allowed shadow-2xs"
            style={{
              backgroundColor: isDark ? "#292929" : "var(--bg-card)",
              borderColor: isDark ? "rgba(255, 255, 255, 0.12)" : "var(--border)",
              color: isDark ? "#FFFFFF" : "var(--text)",
            }}
            title="Next page"
          >
            <ChevronRight className="h-4 w-4" />
          </button>

          {pages.length > 1 && (
            <button
              type="button"
              onClick={() => setShowThumbnails(!showThumbnails)}
              className="w-7 h-7 flex items-center justify-center rounded-btn border transition-colors cursor-pointer shadow-2xs ml-1"
              style={{
                backgroundColor: showThumbnails ? "var(--accent)" : isDark ? "#292929" : "var(--bg-card)",
                borderColor: showThumbnails ? "var(--accent)" : isDark ? "rgba(255, 255, 255, 0.12)" : "var(--border)",
                color: showThumbnails ? "var(--ink)" : isDark ? "#FFFFFF" : "var(--text)",
              }}
              title="Toggle page thumbnails"
            >
              <Layers className="h-3.5 w-3.5" />
            </button>
          )}
        </div>

        {/* Center: Zoom Controls & Fit Actions */}
        <div
          className="flex items-center space-x-1 p-1 rounded-btn border shadow-2xs"
          style={{
            backgroundColor: isDark ? "#292929" : "var(--bg-card)",
            borderColor: isDark ? "rgba(255, 255, 255, 0.12)" : "var(--border)",
          }}
        >
          <button
            type="button"
            onClick={zoomOut}
            className="w-6 h-6 flex items-center justify-center rounded hover:opacity-80 transition-opacity cursor-pointer"
            style={{ color: isDark ? "#E5E5E7" : "var(--text)" }}
            title="Zoom out (-)"
          >
            <ZoomOut className="h-3.5 w-3.5" />
          </button>

          <button
            type="button"
            onClick={resetView}
            className="px-2 py-0.5 rounded font-mono text-[11px] font-semibold transition-opacity cursor-pointer min-w-[44px] text-center"
            style={{ color: isDark ? "#FFFFFF" : "var(--text)" }}
            title="Click to reset (90%)"
          >
            {Math.round(scale * 100)}%
          </button>

          <button
            type="button"
            onClick={zoomIn}
            className="w-6 h-6 flex items-center justify-center rounded hover:opacity-80 transition-opacity cursor-pointer"
            style={{ color: isDark ? "#E5E5E7" : "var(--text)" }}
            title="Zoom in (+)"
          >
            <ZoomIn className="h-3.5 w-3.5" />
          </button>

          <div
            className="h-3.5 w-px mx-1"
            style={{ backgroundColor: isDark ? "rgba(255, 255, 255, 0.15)" : "var(--border)" }}
          />

          <button
            type="button"
            onClick={handleFitWidth}
            className="w-6 h-6 flex items-center justify-center rounded hover:opacity-80 transition-opacity cursor-pointer"
            style={{ color: isDark ? "#E5E5E7" : "var(--text)" }}
            title="Fit Width (W)"
          >
            <ArrowLeftRight className="h-3.5 w-3.5" />
          </button>

          <button
            type="button"
            onClick={handleFitPage}
            className="w-6 h-6 flex items-center justify-center rounded hover:opacity-80 transition-opacity cursor-pointer"
            style={{ color: isDark ? "#E5E5E7" : "var(--text)" }}
            title="Fit Page (0)"
          >
            <Maximize2 className="h-3.5 w-3.5" />
          </button>

          <button
            type="button"
            onClick={rotateClockwise}
            className="w-6 h-6 flex items-center justify-center rounded hover:opacity-80 transition-opacity cursor-pointer"
            style={{ color: isDark ? "#E5E5E7" : "var(--text)" }}
            title="Rotate 90° (R)"
          >
            <RotateCw className="h-3.5 w-3.5" />
          </button>
        </div>

        {/* Right: Theme, Widescreen & Popout */}
        <div className="flex items-center space-x-1.5">
          <button
            type="button"
            onClick={() => setCanvasTheme(isDark ? "desk" : "dark")}
            className="w-7 h-7 flex items-center justify-center rounded-btn border transition-colors cursor-pointer shadow-2xs"
            style={{
              backgroundColor: isDark ? "#292929" : "var(--bg-card)",
              borderColor: isDark ? "rgba(255, 255, 255, 0.12)" : "var(--border)",
              color: isDark ? "var(--warning)" : "var(--text-secondary)",
            }}
            title={isDark ? "Switch to Desk Light" : "Switch to Dark Studio"}
          >
            {isDark ? <Sun className="h-3.5 w-3.5" /> : <Moon className="h-3.5 w-3.5" />}
          </button>

          {onToggleWideMode && (
            <button
              type="button"
              onClick={onToggleWideMode}
              className="w-7 h-7 flex items-center justify-center rounded-btn border transition-colors cursor-pointer shadow-2xs"
              style={{
                backgroundColor: wideMode ? "var(--ink)" : isDark ? "#292929" : "var(--bg-card)",
                borderColor: wideMode ? "var(--ink)" : isDark ? "rgba(255, 255, 255, 0.12)" : "var(--border)",
                color: wideMode ? "#FFFFFF" : isDark ? "#FFFFFF" : "var(--text-secondary)",
              }}
              title={wideMode ? "Standard 50/50 view" : "Wide 62% document view"}
            >
              {wideMode ? <PanelLeftClose className="h-3.5 w-3.5" /> : <PanelLeftOpen className="h-3.5 w-3.5" />}
            </button>
          )}

          <button
            type="button"
            onClick={() => setIsFullscreen(true)}
            className="w-7 h-7 flex items-center justify-center rounded-btn border transition-colors cursor-pointer shadow-2xs"
            style={{
              backgroundColor: isDark ? "#292929" : "var(--bg-card)",
              borderColor: isDark ? "rgba(255, 255, 255, 0.12)" : "var(--border)",
              color: isDark ? "#FFFFFF" : "var(--text-secondary)",
            }}
            title="Fullscreen focus mode"
          >
            <Maximize className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>

      {/* 2. Document Canvas Area */}
      <div
        ref={containerRef}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        onWheel={handleWheel}
        onDoubleClick={handleDoubleClick}
        className={`flex-1 min-h-0 relative overflow-hidden flex items-center justify-center p-6 ${
          isDragging ? "cursor-grabbing" : "cursor-grab"
        } transition-colors duration-200`}
        style={{
          backgroundColor: isDark ? "#1A1A1C" : "var(--bg-app)",
          backgroundImage: isDark
            ? "radial-gradient(#2E2E34 1.5px, transparent 1.5px)"
            : "radial-gradient(#D2D4DC 1.5px, transparent 1.5px)",
          backgroundSize: "24px 24px",
        }}
      >
        {currentImageUrl ? (
          <div
            className="transition-transform duration-75 origin-center flex items-center justify-center will-change-transform"
            style={{
              transform: `translate(${pan.x}px, ${pan.y}px) scale(${scale}) rotate(${rotation}deg)`,
            }}
          >
            <img
              ref={imageRef}
              src={currentImageUrl}
              alt={filename || `Invoice page ${activePage}`}
              onLoad={onImageLoad}
              draggable={false}
              className="max-h-[calc(100vh-10rem)] max-w-[calc(100vw-10rem)] object-contain bg-white rounded-xs shadow-[0_16px_48px_-12px_rgba(0,0,0,0.18),0_2px_10px_rgba(0,0,0,0.06)] border border-border/80 transition-shadow duration-150"
              style={{
                imageRendering: "auto",
              }}
            />
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center space-y-2" style={{ color: "var(--text-muted)" }}>
            <FileText className="h-10 w-10 stroke-1" />
            <p className="text-xs font-medium">No document preview available</p>
          </div>
        )}

        {/* Floating helper pill */}
        <div
          className="absolute bottom-3.5 right-3.5 pointer-events-none opacity-60 hover:opacity-100 transition-opacity backdrop-blur-md text-[11px] font-medium px-3 py-1 rounded-full border shadow-xs flex items-center space-x-2"
          style={{
            backgroundColor: isDark ? "rgba(41, 41, 41, 0.85)" : "rgba(255, 255, 255, 0.9)",
            borderColor: isDark ? "rgba(255, 255, 255, 0.12)" : "var(--border)",
            color: isDark ? "#D1D1D6" : "var(--text-muted)",
          }}
        >
          <span>Ctrl + Scroll to zoom</span>
          <span>•</span>
          <span>Drag to pan</span>
          <span>•</span>
          <span>Double-click to reset</span>
        </div>
      </div>

      {/* 3. Bottom Multi-Page Filmstrip (when toggled or multi-page) */}
      {pages.length > 1 && showThumbnails && (
        <div
          className="h-22 shrink-0 border-t flex items-center px-4 space-x-3 overflow-x-auto z-10 transition-colors shadow-inner"
          style={{
            backgroundColor: isDark ? "#202022" : "var(--bg-card)",
            borderColor: isDark ? "rgba(255, 255, 255, 0.08)" : "var(--border)",
          }}
        >
          {pages.map((p) => {
            const isActive = activePage === p.page_number;
            return (
              <button
                key={p.page_number}
                type="button"
                onClick={() => onPageChange(p.page_number)}
                className="group relative h-16 w-12 rounded border overflow-hidden shrink-0 transition-all cursor-pointer shadow-xs"
                style={{
                  borderColor: isActive ? "var(--accent)" : isDark ? "rgba(255, 255, 255, 0.15)" : "var(--border)",
                  boxShadow: isActive ? "0 0 0 2px var(--accent)" : undefined,
                  opacity: isActive ? 1 : 0.65,
                }}
              >
                <img
                  src={p.url}
                  alt={`Thumbnail page ${p.page_number}`}
                  className="h-full w-full object-cover"
                />
                <div
                  className="absolute bottom-0 inset-x-0 text-[9px] font-mono font-bold text-center py-0.5"
                  style={{
                    backgroundColor: isActive ? "var(--accent)" : isDark ? "rgba(0, 0, 0, 0.8)" : "rgba(255, 255, 255, 0.85)",
                    color: isActive ? "var(--ink)" : isDark ? "#FFFFFF" : "var(--text)",
                  }}
                >
                  P.{p.page_number}
                </div>
              </button>
            );
          })}
        </div>
      )}

      {/* 4. Fullscreen Lightbox Modal */}
      {isFullscreen && (
        <div className="fixed inset-0 z-50 bg-black/90 backdrop-blur-md flex flex-col">
          {/* Fullscreen Toolbar */}
          <div
            className="h-12 px-6 flex items-center justify-between border-b text-white shrink-0"
            style={{
              backgroundColor: "var(--ink)",
              borderColor: "rgba(255, 255, 255, 0.1)",
            }}
          >
            <div className="flex items-center space-x-3">
              <span className="font-semibold text-sm">
                {filename || "Invoice Document Preview"}
              </span>
              <span className="text-xs opacity-60 font-mono">
                Page {activePage} of {totalPages}
              </span>
            </div>

            <div className="flex items-center space-x-2">
              <button
                type="button"
                onClick={zoomOut}
                className="p-1.5 rounded hover:bg-white/10 transition-colors cursor-pointer"
                title="Zoom Out"
              >
                <ZoomOut className="h-4 w-4" />
              </button>
              <span className="font-mono text-xs w-12 text-center">
                {Math.round(scale * 100)}%
              </span>
              <button
                type="button"
                onClick={zoomIn}
                className="p-1.5 rounded hover:bg-white/10 transition-colors cursor-pointer"
                title="Zoom In"
              >
                <ZoomIn className="h-4 w-4" />
              </button>
              <button
                type="button"
                onClick={handleFitWidth}
                className="p-1.5 rounded hover:bg-white/10 transition-colors cursor-pointer"
                title="Fit Width"
              >
                <ArrowLeftRight className="h-4 w-4" />
              </button>
              <button
                type="button"
                onClick={handleFitPage}
                className="p-1.5 rounded hover:bg-white/10 transition-colors cursor-pointer"
                title="Fit Page"
              >
                <Maximize2 className="h-4 w-4" />
              </button>
              <button
                type="button"
                onClick={rotateClockwise}
                className="p-1.5 rounded hover:bg-white/10 transition-colors cursor-pointer"
                title="Rotate 90°"
              >
                <RotateCw className="h-4 w-4" />
              </button>
              <div className="h-4 w-px bg-white/20 mx-2" />
              <button
                type="button"
                onClick={() => setIsFullscreen(false)}
                className="p-1.5 rounded bg-white/10 hover:bg-white/20 flex items-center space-x-1.5 px-3 text-xs font-semibold cursor-pointer transition-colors"
                title="Close Fullscreen (Esc)"
              >
                <X className="h-4 w-4" />
                <span>Close</span>
              </button>
            </div>
          </div>

          {/* Fullscreen Canvas */}
          <div
            onMouseDown={handleMouseDown}
            onMouseMove={handleMouseMove}
            onMouseUp={handleMouseUp}
            onWheel={handleWheel}
            className={`flex-1 overflow-hidden flex items-center justify-center p-8 ${
              isDragging ? "cursor-grabbing" : "cursor-grab"
            }`}
          >
            {currentImageUrl && (
              <div
                style={{
                  transform: `translate(${pan.x}px, ${pan.y}px) scale(${scale}) rotate(${rotation}deg)`,
                }}
                className="transition-transform duration-75 origin-center flex items-center justify-center"
              >
                <img
                  src={currentImageUrl}
                  alt={`Invoice page ${activePage}`}
                  draggable={false}
                  className="max-h-[85vh] max-w-[85vw] object-contain shadow-2xl rounded-xs ring-1 ring-white/10"
                />
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
