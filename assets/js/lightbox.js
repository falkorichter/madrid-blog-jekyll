/*
 * Minimal lightbox for post images and the old NextGEN galleries ([gallery=N]).
 * A click on an image link inside a post opens the full-size image in a <dialog>
 * instead of leaving the page. Unlinked images shown much smaller than their real
 * size open the same way.
 *   Esc / click / ×  close        ← → / swipe  previous / next image of the same post
 * The neighbours are preloaded, so stepping through a gallery is instant.
 * Without JavaScript the links simply open the image.
 */
(function () {
  var IMAGE = /\.(jpe?g|png|gif|webp|bmp)$/i;
  var FILENAME = /^[\w.\- ]+\.(jpe?g|png|gif|webp|bmp)$/i; // alt texts that are just the file name
  var ROOT = ".storycontent";
  if (typeof HTMLDialogElement !== "function") return; // very old browsers: plain links

  var dialog = document.createElement("dialog");
  dialog.className = "lightbox";
  dialog.setAttribute("aria-label", "Bild");
  dialog.innerHTML =
    '<button type="button" class="lightbox-close" aria-label="Schließen">×</button>' +
    '<button type="button" class="lightbox-prev" aria-label="Vorheriges Bild">‹</button>' +
    '<button type="button" class="lightbox-next" aria-label="Nächstes Bild">›</button>' +
    '<figure><img alt="" /><figcaption><span class="lightbox-counter"></span><span class="lightbox-text"></span></figcaption></figure>';
  document.body.appendChild(dialog);

  var img = dialog.querySelector("img");
  var caption = dialog.querySelector("figcaption");
  var counter = dialog.querySelector(".lightbox-counter");
  var captionText = dialog.querySelector(".lightbox-text");
  var prev = dialog.querySelector(".lightbox-prev");
  var next = dialog.querySelector(".lightbox-next");
  var group = [];
  var index = 0;

  function isImageLink(a) {
    return IMAGE.test(a.pathname) && a.origin === location.origin;
  }

  // Unlinked images shown smaller than their real size (e.g. squeezed into the column).
  function isZoomable(image) {
    return !image.closest("a") && image.naturalWidth > image.clientWidth + 40;
  }

  function items(root) {
    return Array.prototype.filter.call(root.querySelectorAll("a[href], img"), function (el) {
      return el.tagName === "A" ? isImageLink(el) : el.classList.contains("zoomable");
    });
  }

  function source(item) {
    return item.tagName === "IMG" ? item.currentSrc || item.src : item.href;
  }

  function describe(item) {
    var thumb = item.tagName === "IMG" ? item : item.querySelector("img");
    var candidates = [item.getAttribute("title"), thumb && thumb.getAttribute("title"), thumb && thumb.getAttribute("alt")];
    for (var i = 0; i < candidates.length; i++) {
      var text = (candidates[i] || "").trim();
      if (text && !FILENAME.test(text) && !/^(image|bild|thumbnail)$/i.test(text)) return text;
    }
    return "";
  }

  function preload(i) {
    if (group.length < 2) return;
    var item = group[(i + group.length) % group.length];
    new Image().src = source(item);
  }

  function show(i) {
    index = (i + group.length) % group.length;
    var item = group[index];
    var text = describe(item);
    dialog.classList.add("is-loading");
    img.onload = img.onerror = function () { dialog.classList.remove("is-loading"); };
    img.src = source(item);
    img.alt = text;
    captionText.textContent = text;
    counter.textContent = group.length > 1 ? index + 1 + " / " + group.length : "";
    caption.hidden = !text && group.length < 2;
    prev.hidden = next.hidden = group.length < 2;
    preload(index + 1);
    preload(index - 1);
  }

  document.addEventListener("click", function (event) {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    if (!event.target.closest) return;
    var item = event.target.closest(ROOT + " a[href]");
    if (item && !isImageLink(item)) return;
    if (!item && event.target.matches(ROOT + " img.zoomable")) item = event.target;
    if (!item) return;
    event.preventDefault();
    group = items(item.closest(ROOT));
    show(group.indexOf(item));
    if (!dialog.open) dialog.showModal();
  });

  dialog.addEventListener("click", function (event) {
    if (event.target === prev) show(index - 1);
    else if (event.target === next) show(index + 1);
    else if (!swiped) dialog.close(); // click on the image, the backdrop or ×
  });

  dialog.addEventListener("keydown", function (event) {
    if (event.key === "ArrowLeft" && group.length > 1) show(index - 1);
    if (event.key === "ArrowRight" && group.length > 1) show(index + 1);
  });

  // Swipe left/right on touch screens.
  var touchX = null;
  var swiped = false;
  dialog.addEventListener("touchstart", function (event) {
    touchX = event.touches.length === 1 ? event.touches[0].clientX : null;
    swiped = false;
  }, { passive: true });
  dialog.addEventListener("touchend", function (event) {
    if (touchX === null || group.length < 2) return;
    var dx = event.changedTouches[0].clientX - touchX;
    if (Math.abs(dx) > 50) {
      swiped = true;
      show(dx < 0 ? index + 1 : index - 1);
      setTimeout(function () { swiped = false; }, 400);
    }
    touchX = null;
  });

  dialog.addEventListener("close", function () { img.removeAttribute("src"); });

  // Mark what opens in the lightbox (zoom cursor).
  function scan() {
    Array.prototype.forEach.call(document.querySelectorAll(ROOT + " a[href]"), function (a) {
      if (isImageLink(a)) a.classList.add("lightbox-link");
    });
    Array.prototype.forEach.call(document.querySelectorAll(ROOT + " img"), function (image) {
      var mark = function () { image.classList.toggle("zoomable", isZoomable(image)); };
      if (image.complete) mark();
      else image.addEventListener("load", mark, { once: true });
    });
  }
  scan();
  window.addEventListener("resize", scan);
})();
