(function () {
  const bootstrap = window.SLIDESHOW_BOOTSTRAP || {};
  const root = document.getElementById("slideshow-root");
  const container = document.getElementById("slide-container");
  const emptyState = document.getElementById("empty-state");

  if (!root || !container || !bootstrap.dataEndpoint) {
    console.warn("Slideshow bootstrap payload missing required elements.");
    return;
  }

  const params = new URLSearchParams(window.location.search);
  const debugMode = params.has("debug");

  const dwellMs = resolvePositive(
    debugMode ? params.get("duration") : bootstrap.dwellMilliseconds,
    bootstrap.dwellMilliseconds || 8000
  );
  const transitionMs = resolvePositive(
    bootstrap.transitionMilliseconds,
    bootstrap.transitionMilliseconds || 800
  );
  const pollSeconds = resolvePositive(
    bootstrap.pollSeconds,
    bootstrap.pollSeconds || 60
  );
  const messageLimit = resolveNonNegative(
    root.dataset.maxMessageLength ?? bootstrap.maxMessageLength
  );

  root.style.setProperty("--slide-transition", `${transitionMs}ms`);

  const shuffleOnce = debugMode && params.get("shuffle") === "true";

  let tributes = [];
  let currentTributeIndex = -1;
  let currentPhotoIndex = 0;
  let currentTributeId = null;
  let rotationTimer = null;
  let pollTimer = null;
  let etag = null;
  let lastModified = null;
  let backoffMultiplier = 1;

  fetchTributes();

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") {
      schedulePoll(500);
      if (getFrameCount() > 0) {
        scheduleRotation();
      }
    } else {
      clearTimeout(rotationTimer);
      clearTimeout(pollTimer);
    }
  });

  if (debugMode) {
    window.addEventListener("keydown", (event) => {
      if (event.key === "ArrowRight") {
        event.preventDefault();
        afterManualNavigation(() => advanceFrame(1));
      }
      if (event.key === "ArrowLeft") {
        event.preventDefault();
        afterManualNavigation(() => advanceFrame(-1));
      }
    });
  }

  function resolvePositive(rawValue, fallback) {
    const numeric = Number.parseInt(rawValue, 10);
    if (!Number.isFinite(numeric) || numeric <= 0) {
      return fallback;
    }
    return numeric;
  }

  function resolveNonNegative(rawValue) {
    const numeric = Number.parseInt(rawValue, 10);
    if (!Number.isFinite(numeric) || numeric < 0) {
      return 0;
    }
    return numeric;
  }

  function afterManualNavigation(callback) {
    clearTimeout(rotationTimer);
    callback();
  }

  function scheduleRotation() {
    clearTimeout(rotationTimer);
    if (getFrameCount() <= 1) {
      return;
    }
    rotationTimer = window.setTimeout(() => advanceFrame(1), dwellMs);
  }

  function schedulePoll(delayMs) {
    clearTimeout(pollTimer);
    pollTimer = window.setTimeout(() => {
      if (document.visibilityState === "hidden") {
        schedulePoll(delayMs);
        return;
      }
      fetchTributes();
    }, Math.max(delayMs, 1000));
  }

  async function fetchTributes() {
    const headers = new Headers();
    if (etag) {
      headers.set("If-None-Match", etag);
    }
    if (lastModified) {
      headers.set("If-Modified-Since", lastModified);
    }

    try {
      const response = await fetch(bootstrap.dataEndpoint, {
        method: "GET",
        headers,
        cache: "no-store"
      });

      if (response.status === 304) {
        backoffMultiplier = 1;
        schedulePoll(pollSeconds * 1000);
        return;
      }

      if (!response.ok) {
        throw new Error(`Request failed with status ${response.status}`);
      }

      etag = response.headers.get("ETag") || etag;
      lastModified = response.headers.get("Last-Modified") || lastModified;

      const payload = await response.json();
      const incoming = Array.isArray(payload.tributes) ? payload.tributes : [];
      const mergeResult = mergeTributes(incoming);

      if (!mergeResult.hasData) {
        clearCurrentSlide();
        schedulePoll(pollSeconds * 1000);
        return;
      }

      if (mergeResult.restartFromFirst) {
        advanceFrame(1);
      } else if (mergeResult.refreshCurrent) {
        const tribute = tributes[currentTributeIndex];
        if (tribute) {
          currentPhotoIndex = Math.min(
            currentPhotoIndex,
            Math.max(tribute.photos.length - 1, 0)
          );
          renderSlide(tribute, currentPhotoIndex);
          scheduleRotation();
        }
      } else if (currentTributeIndex === -1) {
        advanceFrame(1);
      }

      backoffMultiplier = 1;
      schedulePoll(pollSeconds * 1000);
    } catch (error) {
      console.error("Failed to fetch slideshow data", error);
      backoffMultiplier = Math.min(backoffMultiplier * 2, 6);
      schedulePoll(pollSeconds * 1000 * backoffMultiplier);
    }
  }

  function mergeTributes(incoming) {
    if (!incoming.length) {
      tributes = [];
      currentTributeIndex = -1;
      currentPhotoIndex = 0;
      currentTributeId = null;
      updateEmptyState();
      return { hasData: false, restartFromFirst: false, refreshCurrent: false };
    }

    const seen = new Set();
    const sanitized = [];

    for (const raw of incoming) {
      if (!raw || typeof raw !== "object") {
        continue;
      }
      const id = raw.id;
      if (id == null || seen.has(id)) {
        continue;
      }
      seen.add(id);
      sanitized.push(sanitizeTribute(raw));
    }

    sanitized.sort((a, b) => {
      const left = Date.parse(b.created_at || "");
      const right = Date.parse(a.created_at || "");
      return (Number.isFinite(left) ? left : 0) - (Number.isFinite(right) ? right : 0);
    });

    if (shuffleOnce) {
      shuffleArray(sanitized);
    }

    const previousId = currentTributeId;
    tributes = sanitized;
    updateEmptyState();

    if (!tributes.length) {
      currentTributeIndex = -1;
      currentPhotoIndex = 0;
      currentTributeId = null;
      return { hasData: false, restartFromFirst: false, refreshCurrent: false };
    }

    const locatedIndex = previousId != null
      ? tributes.findIndex((entry) => entry.id === previousId)
      : -1;

    if (locatedIndex !== -1) {
      currentTributeIndex = locatedIndex;
      currentTributeId = tributes[locatedIndex].id;
      currentPhotoIndex = Math.min(
        currentPhotoIndex,
        Math.max(tributes[locatedIndex].photos.length - 1, 0)
      );
      return { hasData: true, restartFromFirst: false, refreshCurrent: true };
    }

    currentTributeIndex = -1;
    currentPhotoIndex = 0;
    currentTributeId = null;
    return { hasData: true, restartFromFirst: true, refreshCurrent: false };
  }

  function sanitizeTribute(raw) {
    const message = typeof raw.message === "string" ? raw.message.trim() : "";
    const name = raw.name ? String(raw.name) : "Anonymous";
    const created = raw.created_at || new Date().toISOString();
    const photos = Array.isArray(raw.photos) ? raw.photos : [];
    const usablePhotos = photos
      .map((photo) => ({
        id: photo && photo.id != null ? photo.id : null,
        url: photo && typeof photo.url === "string" ? photo.url : null,
        caption: photo && typeof photo.caption === "string" ? photo.caption : "",
        content_type: photo && photo.content_type ? String(photo.content_type) : null
      }))
      .filter((photo) => Boolean(photo.url));

    return {
      id: raw.id,
      name,
      message,
      created_at: created,
      photos: usablePhotos,
      text_only: raw.text_only || usablePhotos.length === 0
    };
  }

  function advanceFrame(step) {
    if (!tributes.length) {
      return;
    }
    let movement = Number.isInteger(step) ? step : 1;
    if (movement === 0) {
      return;
    }

    while (movement !== 0) {
      if (movement > 0) {
        stepForward();
        movement -= 1;
      } else {
        stepBackward();
        movement += 1;
      }
    }

    const tribute = tributes[currentTributeIndex];
    if (tribute) {
      renderSlide(tribute, currentPhotoIndex);
      scheduleRotation();
    }
  }

  function stepForward() {
    if (currentTributeIndex === -1) {
      currentTributeIndex = 0;
      currentPhotoIndex = 0;
      currentTributeId = tributes[0].id;
      return;
    }

    const tribute = tributes[currentTributeIndex];
    const photoCount = tribute.photos.length;

    if (photoCount > 0 && currentPhotoIndex < photoCount - 1) {
      currentPhotoIndex += 1;
      return;
    }

    currentTributeIndex = (currentTributeIndex + 1) % tributes.length;
    currentPhotoIndex = 0;
    currentTributeId = tributes[currentTributeIndex].id;
  }

  function stepBackward() {
    if (currentTributeIndex === -1) {
      currentTributeIndex = tributes.length - 1;
      const tribute = tributes[currentTributeIndex];
      currentPhotoIndex = Math.max(tribute.photos.length - 1, 0);
      currentTributeId = tribute.id;
      return;
    }

    const tribute = tributes[currentTributeIndex];
    if (tribute.photos.length > 0 && currentPhotoIndex > 0) {
      currentPhotoIndex -= 1;
      return;
    }

    currentTributeIndex = (currentTributeIndex - 1 + tributes.length) % tributes.length;
    const previous = tributes[currentTributeIndex];
    currentPhotoIndex = Math.max(previous.photos.length - 1, 0);
    currentTributeId = previous.id;
  }

  function renderSlide(tribute, photoIndex) {
    if (!tribute) {
      return;
    }

    currentTributeId = tribute.id;

    const nextSlide = buildSlideElement(tribute, photoIndex);
    nextSlide.style.setProperty("--slide-transition", `${transitionMs}ms`);

    container.replaceChildren(nextSlide);
    window.requestAnimationFrame(() => {
      nextSlide.classList.add("is-visible");
    });

    updateEmptyState();
    preloadUpcoming();
  }

  function buildSlideElement(tribute, photoIndex) {
    const article = document.createElement("article");
    article.className = "slide";

    const photo = selectPhoto(tribute, photoIndex);
    if (!photo) {
      article.classList.add("slide--text-only");
    }

    const frame = document.createElement("div");
    frame.className = "slide__inner";
    article.appendChild(frame);

    if (photo) {
      const media = document.createElement("figure");
      media.className = "slide__media";

      const img = document.createElement("img");
      img.className = "slide__image";
      img.src = photo.url;
      img.alt = photo.caption || `Tribute photo for ${tribute.name}`;
      const initialLoad = container.childElementCount === 0;
      img.loading = initialLoad ? "eager" : "lazy";
      img.decoding = "async";
      media.appendChild(img);

      frame.appendChild(media);
    }

    const content = document.createElement("div");
    content.className = "slide__content";
    frame.appendChild(content);

    const header = document.createElement("header");
    header.className = "slide__header";

    const nameEl = document.createElement("h2");
    nameEl.className = "slide__name";
    nameEl.textContent = tribute.name;
    header.appendChild(nameEl);

    const timestampEl = document.createElement("time");
    timestampEl.className = "slide__timestamp";
    const timestampText = formatTimestamp(tribute.created_at);
    if (timestampText) {
      timestampEl.textContent = timestampText;
      try {
        timestampEl.dateTime = new Date(tribute.created_at).toISOString();
      } catch (_err) {
        timestampEl.dateTime = "";
      }
    }
    header.appendChild(timestampEl);
    content.appendChild(header);

    const messageInfo = truncateMessage(tribute.message, messageLimit);
    const messageEl = document.createElement("p");
    messageEl.className = "slide__message";
    messageEl.textContent = messageInfo.text;
    messageEl.dataset.truncated = String(messageInfo.truncated);
    messageEl.dataset.fullMessage = messageInfo.full;
    if (messageInfo.full) {
      messageEl.title = messageInfo.full;
    }
    content.appendChild(messageEl);

    if (photo && photo.caption) {
      const captionEl = document.createElement("p");
      captionEl.className = "slide__caption";
      captionEl.textContent = photo.caption;
      content.appendChild(captionEl);
    }

    if (photo && tribute.photos.length > 1) {
      const meta = document.createElement("div");
      meta.className = "slide__meta";
      const status = document.createElement("span");
      status.textContent = `Photo ${photoIndex + 1} of ${tribute.photos.length}`;
      meta.appendChild(status);
      content.appendChild(meta);
    }

    return article;
  }

  function selectPhoto(tribute, photoIndex) {
    if (!tribute || !Array.isArray(tribute.photos) || tribute.photos.length === 0) {
      return null;
    }
    const clampedIndex = Math.max(0, Math.min(photoIndex || 0, tribute.photos.length - 1));
    return tribute.photos[clampedIndex];
  }

  function formatTimestamp(value) {
    try {
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) {
        throw new Error("Invalid date");
      }
      return new Intl.DateTimeFormat(undefined, {
        dateStyle: "long",
        timeStyle: "short"
      }).format(date);
    } catch (_err) {
      return "";
    }
  }

  function truncateMessage(message, limit) {
    const safeMessage = typeof message === "string" ? message.trim() : "";
    if (!limit || limit <= 0 || safeMessage.length <= limit) {
      return { text: safeMessage, full: safeMessage, truncated: false };
    }

    let truncated = safeMessage.slice(0, limit);
    const lastSpace = truncated.lastIndexOf(" ");
    if (lastSpace > Math.floor(limit * 0.6)) {
      truncated = truncated.slice(0, lastSpace);
    }
    truncated = truncated.replace(/[\s,;:-]+$/u, "");

    return {
      text: `${truncated}...`,
      full: safeMessage,
      truncated: true
    };
  }

  function preloadUpcoming() {
    const peek = advanceIndices(currentTributeIndex, currentPhotoIndex, 1);
    if (peek.tributeIndex === -1) {
      return;
    }
    const upcomingTribute = tributes[peek.tributeIndex];
    const upcomingPhoto = selectPhoto(upcomingTribute, peek.photoIndex);
    if (upcomingPhoto && upcomingPhoto.url) {
      const img = new Image();
      img.src = upcomingPhoto.url;
    }
  }

  function advanceIndices(tributeIndex, photoIndex, direction) {
    if (!tributes.length) {
      return { tributeIndex: -1, photoIndex: 0 };
    }

    let idx = tributeIndex;
    let pIdx = photoIndex;
    let remaining = direction >= 0 ? direction : -direction;
    const step = direction >= 0 ? 1 : -1;

    while (remaining > 0) {
      if (step > 0) {
        if (idx === -1) {
          idx = 0;
          pIdx = 0;
        } else {
          const tribute = tributes[idx];
          const photoCount = tribute.photos.length;
          if (photoCount > 0 && pIdx < photoCount - 1) {
            pIdx += 1;
          } else {
            idx = (idx + 1) % tributes.length;
            pIdx = 0;
          }
        }
      } else {
        if (idx === -1) {
          idx = tributes.length - 1;
          const tribute = tributes[idx];
          pIdx = Math.max(tribute.photos.length - 1, 0);
        } else {
          const tribute = tributes[idx];
          if (tribute.photos.length > 0 && pIdx > 0) {
            pIdx -= 1;
          } else {
            idx = (idx - 1 + tributes.length) % tributes.length;
            const prev = tributes[idx];
            pIdx = Math.max(prev.photos.length - 1, 0);
          }
        }
      }
      remaining -= 1;
    }

    return { tributeIndex: idx, photoIndex: pIdx };
  }

  function getFrameCount() {
    return tributes.reduce((total, tribute) => {
      const photoCount = Array.isArray(tribute.photos) && tribute.photos.length
        ? tribute.photos.length
        : 1;
      return total + photoCount;
    }, 0);
  }

  function shuffleArray(list) {
    for (let i = list.length - 1; i > 0; i -= 1) {
      const j = Math.floor(Math.random() * (i + 1));
      const temp = list[i];
      list[i] = list[j];
      list[j] = temp;
    }
  }

  function clearCurrentSlide() {
    container.innerHTML = "";
    currentTributeId = null;
    currentTributeIndex = -1;
    currentPhotoIndex = 0;
    updateEmptyState();
  }

  function updateEmptyState() {
    if (!emptyState) {
      return;
    }
    if (getFrameCount() === 0) {
      emptyState.classList.remove("hidden");
    } else {
      emptyState.classList.add("hidden");
    }
  }
})();
