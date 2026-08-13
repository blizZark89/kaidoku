function onBlockLoad() {
  var infor_panel_scroll_pos = 0;
  globalThis.createModal = () => {
    // Create modal for the 1st time if it does not exist
    var modal = document.getElementById("pdf-modal");
    var old_position = null;
    var old_width = null;
    var old_left = null;
    var expanded = false;

    modal.id = "pdf-modal";
    modal.className = "modal";
    modal.innerHTML = [
      '<div class="modal-content">',
      '  <div class="modal-header">',
      '    <span class="close" id="modal-close">&times;</span>',
      '    <span class="close" id="modal-expand">&#x26F6;</span>',
      '  </div>',
      '  <div class="modal-body">',
      '    <iframe id="pdf-viewer" style="width:100%;height:100%;border:none"></iframe>',
      '  </div>',
      '</div>',
    ].join('\n');

    modal.querySelector("#modal-close").onclick = function () {
      modal.style.display = "none";
      var info_panel = document.getElementById("html-info-panel");
      if (info_panel) {
        info_panel.style.display = "block";
      }
      var scrollableDiv = document.getElementById("chat-info-panel");
      scrollableDiv.scrollTop = infor_panel_scroll_pos;
    };

    modal.querySelector("#modal-expand").onclick = function () {
      expanded = !expanded;
      if (expanded) {
        old_position = modal.style.position;
        old_left = modal.style.left;
        old_width = modal.style.width;

        modal.style.position = "fixed";
        modal.style.width = "70%";
        modal.style.left = "15%";
        modal.style.height = "100vh";
      } else {
        modal.style.position = old_position;
        modal.style.width = old_width;
        modal.style.left = old_left;
        modal.style.height = "85vh";
      }
    };
  };

  // Function to open modal and display PDF
  globalThis.openModal = (event) => {
    event.preventDefault();
    var target = event.currentTarget;
    var src = target.getAttribute("data-src");
    var page = target.getAttribute("data-page");

    var pdfUrl = page ? src + "#page=" + page : src;

    var iframe = document.getElementById("pdf-viewer");
    if (!iframe) return;

    // Replace the iframe element entirely. The browser's built-in PDF viewer
    // keeps internal state (scroll position, loaded document) tied to the
    // iframe element — changing src, using location.replace(), or cache-bust
    // query params are all unreliable across browsers. Removing the iframe
    // from the DOM and inserting a fresh one guarantees the PDF viewer starts
    // clean and honors the #page=N fragment. A cache-bust query is kept as
    // well so the document itself is re-fetched instead of served from
    // HTTP cache with stale viewer state.
    var parent = iframe.parentNode;
    var fresh = document.createElement("iframe");
    fresh.id = "pdf-viewer";
    fresh.style.width = "100%";
    fresh.style.height = "100%";
    fresh.style.border = "none";
    var url = page
      ? src + (src.indexOf("?") === -1 ? "?" : "&") + "p=" + page + "&t=" + Date.now() + "#page=" + page
      : pdfUrl;
    parent.removeChild(iframe);
    fresh.src = url;
    parent.appendChild(fresh);

    var scrollableDiv = document.getElementById("chat-info-panel");
    infor_panel_scroll_pos = scrollableDiv.scrollTop;

    var modal = document.getElementById("pdf-modal");
    modal.style.display = "block";
    var info_panel = document.getElementById("html-info-panel");
    if (info_panel) {
      info_panel.style.display = "none";
    }
    scrollableDiv.scrollTop = 0;
  };

  globalThis.assignPdfOnclickEvent = () => {
    // Get all links and attach click event
    var links = document.getElementsByClassName("pdf-link");
    for (var i = 0; i < links.length; i++) {
      links[i].onclick = openModal;
    }
  };

  var created_modal = document.getElementById("pdf-viewer");
  if (!created_modal) {
    createModal();
  }
}