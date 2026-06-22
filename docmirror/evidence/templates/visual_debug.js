(function() {
  var G = window.VISUAL_EVIDENCE_GRAPH || {};
  var M = window.OVERLAY_MANIFEST || {};
  var overlays = M.overlays || [];
  var layers = M.layers || [];
  var nodes = G.nodes || {};
  var pages = G.pages || [];
  var DPI_SCALE = 150 / 72;

  var currentPage = 1;
  var layerVisibility = {};
  layers.forEach(function(l) { layerVisibility[l.id] = l.default_visible !== false; });

  function renderPageList() {
    var el = document.getElementById("page-list");
    var html = "";
    var pageSet = {};
    overlays.forEach(function(o) { pageSet[o.page] = true; });
    var nums = Object.keys(pageSet).map(Number).sort(function(a,b) { return a-b; });
    if (nums.length === 0 && pages.length > 0) {
      pages.forEach(function(p) { nums.push(p.page); });
    }
    if (nums.length === 0) nums = [1];
    nums.forEach(function(pn) {
      var cls = (pn === currentPage) ? "page-thumb active" : "page-thumb";
      html += '<div class="' + cls + '" data-page="' + pn + '" onclick="window._selectPage(' + pn + ')">Page ' + pn + '</div>';
    });
    el.innerHTML = html;
  }

  function renderPageImage() {
    var img = document.getElementById("page-image");
    var pn = String(currentPage).padStart(3, "0");
    img.src = "page_images/page_" + pn + ".png";
    img.style.display = "block";
    img.onload = function() { renderOverlays(); };
    img.onerror = function() {
      img.style.display = "none";
      renderOverlays();
    };
  }

  function renderOverlays() {
    var svg = document.getElementById("overlay-svg");
    var img = document.getElementById("page-image");
    var pageOv = overlays.filter(function(o) { return o.page === currentPage; });

    var imgW = img.naturalWidth || 800;
    var imgH = img.naturalHeight || 1100;
    svg.setAttribute("width", imgW);
    svg.setAttribute("height", imgH);

    var svgNS = "http://www.w3.org/2000/svg";
    while (svg.firstChild) svg.removeChild(svg.firstChild);

    pageOv.forEach(function(o) {
      var lid = o.layer || "blocks";
      if (!layerVisibility[lid]) return;
      var bbox = o.bbox || [0,0,0,0];
      var x = bbox[0] * DPI_SCALE;
      var y = bbox[1] * DPI_SCALE;
      var w = (bbox[2] - bbox[0]) * DPI_SCALE;
      var h = (bbox[3] - bbox[1]) * DPI_SCALE;
      if (w <= 0 || h <= 0) return;

      var style = o.style || {};
      var rect = document.createElementNS(svgNS, "rect");
      rect.setAttribute("x", String(x));
      rect.setAttribute("y", String(y));
      rect.setAttribute("width", String(w));
      rect.setAttribute("height", String(h));
      rect.setAttribute("fill", style.fill || "rgba(84,174,255,0.08)");
      rect.setAttribute("stroke", style.stroke || "#54aeff");
      rect.setAttribute("stroke-width", String(style.strokeWidth || 1));
      if (style.dash && style.dash.length > 0) {
        rect.setAttribute("stroke-dasharray", style.dash.join(","));
      }
      rect.setAttribute("data-node-id", o.node_id || "");
      rect.setAttribute("data-layer", lid);
      rect.setAttribute("data-kind", o.kind || "");
      rect.addEventListener("click", function() { inspectNode(o); });
      svg.appendChild(rect);

      if (w > 30 && h > 12) {
        var text = document.createElementNS(svgNS, "text");
        text.setAttribute("x", String(x + 2));
        text.setAttribute("y", String(y + 10));
        text.setAttribute("fill", style.stroke || "#c9d1d9");
        text.setAttribute("font-size", "9");
        text.textContent = (o.label || "").substring(0, 20);
        svg.appendChild(text);
      }
    });
  }

  function renderLayerBar() {
    var el = document.getElementById("layer-bar");
    var html = "";
    layers.forEach(function(l) {
      var checked = layerVisibility[l.id] ? " checked" : "";
      var cls = layerVisibility[l.id] ? "layer-toggle active" : "layer-toggle";
      html += '<label class="' + cls + '"><input type="checkbox" data-layer="' + l.id + '"' + checked + ' onchange="window._toggleLayer(this)">' + (l.label || l.id) + '</label>';
    });
    el.innerHTML = html;
  }

  function inspectNode(overlay) {
    var empty = document.getElementById("inspector-empty");
    var content = document.getElementById("inspector-content");
    empty.style.display = "none";
    content.style.display = "block";
    var nid = overlay.node_id || "";
    var node = nodes[nid] || {};

    function row(label, value, cls) {
      var cssClass = cls ? ' ' + cls : '';
      return '<div class="inspector-section"><div class="inspector-label">' + label + '</div><div class="inspector-value' + cssClass + '">' + (value || '--') + '</div></div>';
    }

    var review = overlay.review || node.review || "auto_accepted";
    var reviewBadge = "";
    if (review !== "auto_accepted") {
      reviewBadge = ' <span class="badge review-' + review + '">' + review + '</span>';
    }

    var html = "";
    html += row("Node ID", esc(nid));
    html += row("Kind", esc(overlay.kind || node.kind || ""), "kind");
    html += row("Label", esc(overlay.label || node.label || ""));
    if (node.field_path || overlay.field_path) {
      html += row("Field Path", esc(node.field_path || overlay.field_path || ""), "field-path");
    }
    var conf = (overlay.confidence != null ? overlay.confidence : node.confidence) || 0;
    html += row("Confidence", String(conf));
    html += '<div class="inspector-section"><div class="inspector-label">Review</div><div class="inspector-value">' + esc(review) + reviewBadge + '</div></div>';
    html += row("Page", String(overlay.page || node.page || ""));
    html += row("BBox", (overlay.bbox || node.bbox || []).join(", "));
    if (overlay.tooltip) {
      html += row("Tooltip", esc(overlay.tooltip));
    }
    if (node.source_refs && node.source_refs.length > 0) {
      html += row("Source Refs", node.source_refs.join(", "));
    }
    if (node.edition) {
      html += row("Edition", esc(node.edition));
    }
    if (node.value_preview) {
      html += row("Value Preview", esc(node.value_preview));
    }
    content.innerHTML = html;
  }

  function esc(str) {
    return String(str || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }

  window._selectPage = function(pn) {
    currentPage = pn;
    renderPageList();
    renderPageImage();
  };
  window._toggleLayer = function(cb) {
    var lid = cb.getAttribute("data-layer");
    layerVisibility[lid] = cb.checked;
    renderLayerBar();
    renderOverlays();
  };

  renderPageList();
  renderLayerBar();
  renderPageImage();
})();
