/**
 * Legal Metrology Compliance Portal — Officer Frontend Application Logic
 * Department of Consumer Affairs / Government of India
 *
 * Final Integration Pass: Direct communication with existing FastAPI backend endpoints
 * - Relative URLs: /api/scan, /api/scan-url, /api/scans, /api/reports/pdf
 * - Zero hardcoded mock results; purely displays backend response contracts
 */

const API_BASE_URL = typeof window !== 'undefined' && window.location.origin.startsWith('http') ? window.location.origin : 'https://packsure-production-ce7f.up.railway.app';

// Statutory PCR 2011 Rule Mapping for Physical Package Inspection
const PACKAGE_RULE_DEFINITIONS = [
  {
    key: "1_manufacturer_packer_importer",
    label: "Manufacturer / Packer / Importer Name & Address",
    clause: "Rule 6(1)(a)"
  },
  {
    key: "2_country_of_origin",
    label: "Country of Origin",
    clause: "Rule 6(1)(n)"
  },
  {
    key: "3_generic_common_name",
    label: "Common / Generic Commodity Name",
    clause: "Rule 6(1)(b)"
  },
  {
    key: "4_net_quantity",
    label: "Net Quantity Declaration",
    clause: "Rule 6(1)(c) & Rules 11–13"
  },
  {
    key: "5_manufacture_packing_date",
    label: "Month & Year of Manufacture / Packing",
    clause: "Rule 6(1)(d)"
  },
  {
    key: "6_expiry_best_before",
    label: "Expiry / Best Before Date",
    clause: "Rule 6(1)(m)"
  },
  {
    key: "7_mrp",
    label: "Maximum Retail Price (MRP)",
    clause: "Rule 6(1)(e)"
  },
  {
    key: "8_unit_sale_price",
    label: "Unit Sale Price (USP)",
    clause: "Rule 6(1)(k)"
  },
  {
    key: "9_consumer_care",
    label: "Consumer Care Contact Details",
    clause: "Rule 6(1)(j)"
  }
];

// E-Commerce Listing Rule Definitions (Rule 6(10))
const ECOM_RULE_DEFINITIONS = [
  {
    key: "mrp",
    label: "Maximum Retail Price (MRP)",
    clause: "Rule 6(10) & Section 18"
  },
  {
    key: "net_quantity",
    label: "Net Quantity",
    clause: "Rule 6(10) & Rule 6(1)(c)"
  },
  {
    key: "country_of_origin",
    label: "Country of Origin",
    clause: "Rule 6(10) & Rule 6(1)(n)"
  },
  {
    key: "manufacturer",
    label: "Manufacturer / Packer / Importer",
    clause: "Rule 6(10) & Rule 6(1)(a)"
  },
  {
    key: "consumer_care",
    label: "Consumer Care Contact",
    clause: "Rule 6(10) & Rule 6(1)(j)"
  },
  {
    key: "generic_name",
    label: "Generic / Common Commodity Name",
    clause: "Rule 6(10) & Rule 6(1)(b)"
  }
];

// Active Session State
let activeScanId = null;
let lastScanType = "package";

// =============================================================================
// INITIALIZATION
// =============================================================================
document.addEventListener("DOMContentLoaded", () => {
  if (typeof analysisWorkflow !== "undefined") {
    analysisWorkflow.init();
  }
  setupLandingPage();
  setupAuth();
  setupNavigation();
  setupPackageScanner();
  setupUrlScanner();
  setupPdfReportDownload();

  // Restore existing session if found
  const savedOfficer = sessionStorage.getItem("officer_id");
  if (savedOfficer) {
    displayAuthenticatedSession(savedOfficer);
  } else {
    const landingPage = document.getElementById("packsure-landing");
    if (landingPage) landingPage.style.display = "block";
    const loginScreen = document.getElementById("screen-login");
    if (loginScreen) loginScreen.style.display = "none";
    const appShell = document.getElementById("app-shell");
    if (appShell) appShell.style.display = "none";
  }
});

// =============================================================================
// 0. LANDING PAGE CONTROLLER
// =============================================================================
function setupLandingPage() {
  const landingPage = document.getElementById("packsure-landing");
  const loginScreen = document.getElementById("screen-login");
  const backBtn = document.getElementById("btn-back-to-landing");

  function openLogin() {
    if (landingPage) landingPage.style.display = "none";
    if (loginScreen) {
      loginScreen.style.display = "flex";
      window.scrollTo({ top: 0, behavior: "smooth" });
      const officerInput = document.getElementById("login-officer-id");
      if (officerInput) {
        setTimeout(() => officerInput.focus(), 100);
      }
    }
  }

  function backToLanding() {
    if (loginScreen) loginScreen.style.display = "none";
    if (landingPage) {
      landingPage.style.display = "block";
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
  }

  // Hook landing login CTA buttons
  const loginButtons = [
    document.getElementById("packsure-login-btn"),
    document.getElementById("packsure-hero-login-btn"),
    document.getElementById("packsure-cta-login-btn"),
    document.getElementById("packsure-mobile-login-btn")
  ];
  loginButtons.forEach((btn) => {
    if (btn) {
      btn.addEventListener("click", openLogin);
    }
  });

  // Hook Back to Home on Login Screen
  if (backBtn) {
    backBtn.addEventListener("click", backToLanding);
  }

  // Hook Mobile menu drawer
  const menuBtn = document.getElementById("packsure-mobile-menu-btn");
  const mobileNav = document.getElementById("packsure-mobile-nav");
  if (menuBtn && mobileNav) {
    menuBtn.addEventListener("click", () => {
      mobileNav.classList.toggle("active");
    });
    mobileNav.querySelectorAll("a").forEach((link) => {
      link.addEventListener("click", () => {
        mobileNav.classList.remove("active");
      });
    });
  }
}

// =============================================================================
// 1. OFFICER AUTHENTICATION FLOW
// =============================================================================
function setupAuth() {
  const loginForm = document.getElementById("login-form");
  const loginIdInput = document.getElementById("login-officer-id");
  const passwordInput = document.getElementById("login-password");
  const errorMsg = document.getElementById("login-error-msg");
  const logoutBtn = document.getElementById("btn-logout");

  if (loginForm) {
    loginForm.addEventListener("submit", (e) => {
      e.preventDefault();
      const enteredId = loginIdInput.value.trim();
      const enteredPass = passwordInput.value;

      // Demo authentication credential check
      const isValid =
        (enteredId === "officer.demo" && enteredPass === "Demo@123") ||
        (enteredId === "LMO1024" && enteredPass === "Metro#2024");

      if (isValid) {
        errorMsg.textContent = "";
        sessionStorage.setItem("officer_id", enteredId);
        displayAuthenticatedSession(enteredId);
      } else {
        errorMsg.textContent = "Invalid Login ID or Password.";
      }
    });
  }

  if (logoutBtn) {
    logoutBtn.addEventListener("click", () => {
      sessionStorage.removeItem("officer_id");
      document.getElementById("app-shell").style.display = "none";
      document.getElementById("screen-login").style.display = "none";
      const landingPage = document.getElementById("packsure-landing");
      if (landingPage) landingPage.style.display = "block";
      loginIdInput.value = "";
      passwordInput.value = "";
      errorMsg.textContent = "";
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  }
}

function displayAuthenticatedSession(officerId) {
  const landingPage = document.getElementById("packsure-landing");
  if (landingPage) landingPage.style.display = "none";
  document.getElementById("screen-login").style.display = "none";
  document.getElementById("app-shell").style.display = "block";
  document.getElementById("header-officer-id").textContent = officerId;
  showScreen("screen-dashboard");
  loadDashboardScans();
}

// =============================================================================
// NAVIGATION CONTROLLER
// =============================================================================
function setupNavigation() {
  const navPackageBtn = document.getElementById("nav-btn-scan-package");
  const navUrlBtn = document.getElementById("nav-btn-scan-url");
  const backBtns = document.querySelectorAll(".btn-nav-dashboard");
  const scanAnotherBtn = document.getElementById("btn-scan-another");

  if (navPackageBtn) {
    navPackageBtn.addEventListener("click", () => {
      lastScanType = "package";
      showScreen("screen-scan-package");
    });
  }

  if (navUrlBtn) {
    navUrlBtn.addEventListener("click", () => {
      lastScanType = "url";
      showScreen("screen-scan-url");
    });
  }

  backBtns.forEach((btn) => {
    btn.addEventListener("click", () => {
      showScreen("screen-dashboard");
      loadDashboardScans();
    });
  });

  if (scanAnotherBtn) {
    scanAnotherBtn.addEventListener("click", () => {
      if (lastScanType === "url") {
        showScreen("screen-scan-url");
      } else {
        showScreen("screen-scan-package");
      }
    });
  }
}

function showScreen(screenId) {
  if (screenId !== "screen-scan-package" && typeof analysisWorkflow !== "undefined") {
    analysisWorkflow.reset();
  }

  const screens = [
    "screen-dashboard",
    "screen-scan-package",
    "screen-scan-url",
    "screen-audit-result"
  ];

  screens.forEach((id) => {
    const el = document.getElementById(id);
    if (el) {
      el.style.display = id === screenId ? "block" : "none";
    }
  });

  window.scrollTo(0, 0);
}

// =============================================================================
// 2. OFFICER DASHBOARD: GET /api/scans
// =============================================================================
async function loadDashboardScans() {
  const tbody = document.getElementById("dashboard-scans-tbody");
  if (!tbody) return;

  try {
    const res = await fetch(`${API_BASE_URL}/api/scans?page=1&page_size=25`);
    if (!res.ok) {
      const errMsg = await parseHttpError(res);
      tbody.innerHTML = `<tr><td colspan="6" class="table-empty-msg">${escapeHtml(errMsg)}</td></tr>`;
      return;
    }

    const data = await res.json();
    const items = data.items || [];

    if (items.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" class="table-empty-msg">No inspection records on file.</td></tr>`;
      return;
    }

    tbody.innerHTML = "";
    items.forEach((scan) => {
      const tr = document.createElement("tr");

      const scoreVal = typeof scan.compliance_score === "number" ? scan.compliance_score : null;
      const scoreText = scoreVal !== null ? `${scoreVal.toFixed(2)}%` : "—";
      const statusRaw = String(scan.compliance_status || "COMPLIANT").toUpperCase();

      let badgeClass = "badge-pass";
      let statusText = "PASS";
      if (statusRaw === "NON_COMPLIANT" || statusRaw === "NON-COMPLIANT" || statusRaw === "FAIL") {
        badgeClass = "badge-fail";
        statusText = "FAIL";
      } else if (statusRaw === "WARNING" || statusRaw === "PARTIALLY_COMPLIANT" || statusRaw === "REVIEW_REQUIRED") {
        badgeClass = "badge-warn";
        statusText = "WARNING";
      }

      const dateStr = scan.created_at ? scan.created_at.substring(0, 16).replace("T", " ") : "—";
      const shortId = scan.id ? `${scan.id.substring(0, 8)}...` : "—";

      tr.innerHTML = `
        <td><span class="table-code">${escapeHtml(shortId)}</span></td>
        <td><strong>${escapeHtml(scan.filename || "packaging_label.jpg")}</strong></td>
        <td>${escapeHtml(dateStr)}</td>
        <td><strong>${escapeHtml(scoreText)}</strong></td>
        <td><span class="status-badge ${badgeClass}">${escapeHtml(statusText)}</span></td>
        <td><button type="button" class="btn-link" onclick="viewAuditRecord('${escapeHtml(scan.id)}')">View Audit</button></td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    console.error("Dashboard scan fetch error:", err);
    tbody.innerHTML = `<tr><td colspan="6" class="table-empty-msg">Network error: Unable to connect to verification server.</td></tr>`;
  }
}

// Global viewer for dashboard records
window.viewAuditRecord = async function (scanId) {
  try {
    const res = await fetch(`${API_BASE_URL}/api/scans/${scanId}`);
    if (!res.ok) {
      const errMsg = await parseHttpError(res);
      throw new Error(errMsg);
    }

    const scan = await res.json();
    lastScanType = "package";
    renderPackageAuditResult(scan, {
      compliance: {
        score: scan.compliance_score,
        status: scan.compliance_status,
        violations: scan.violations
      },
      declarations: scan.declarations,
      fields: scan.fields
    });
    showScreen("screen-audit-result");
  } catch (err) {
    alert(`Inspection Load Error: ${err.message}`);
  }
};

// =============================================================================
// PACKAGE SCAN ANALYSIS WORKFLOW CONTROLLER
// =============================================================================
const analysisWorkflow = {
  container: null,
  timerEl: null,
  steps: [],
  step4Title: null,
  step4Sub: null,
  cachedBadge: null,
  startTime: 0,
  timerInterval: null,
  stageTimeouts: [],

  init() {
    this.container = document.getElementById("package-analysis-workflow");
    this.timerEl = document.getElementById("analysis-timer");
    this.steps = [
      document.getElementById("wf-step-1"),
      document.getElementById("wf-step-2"),
      document.getElementById("wf-step-3"),
      document.getElementById("wf-step-4"),
    ];
    this.step4Title = document.getElementById("wf-step-4-title");
    this.step4Sub = document.getElementById("wf-step-4-sub");
    this.cachedBadge = document.getElementById("workflow-cached-badge");
  },

  formatTime(ms) {
    const totalSecs = Math.floor(Math.max(0, ms) / 1000);
    const hours = Math.floor(totalSecs / 3600);
    const mins = Math.floor((totalSecs % 3600) / 60);
    const secs = totalSecs % 60;
    const pad = (n) => String(n).padStart(2, "0");
    if (hours > 0) {
      return `${pad(hours)}:${pad(mins)}:${pad(secs)}`;
    }
    return `${pad(mins)}:${pad(secs)}`;
  },

  setStepState(index, state) {
    if (!this.steps || this.steps.length === 0) this.init();
    if (this.steps[index]) {
      this.steps[index].setAttribute("data-state", state);
    }
    const marker = document.getElementById(`wf-marker-${index + 1}`);
    if (marker) {
      if (state === "completed") {
        marker.textContent = "✓";
        marker.style.color = "var(--green, #106B36)";
        marker.style.fontWeight = "700";
      } else if (state === "active") {
        marker.textContent = "●";
        marker.style.color = "var(--navy, #13284B)";
        marker.style.fontWeight = "700";
      } else {
        marker.textContent = "○";
        marker.style.color = "var(--border, #C7C2B4)";
        marker.style.fontWeight = "400";
      }
    }
  },

  start() {
    this.reset();
    if (!this.container || !this.timerEl) this.init();
    if (!this.container) return;

    this.container.style.display = "block";
    if (this.cachedBadge) this.cachedBadge.style.display = "none";
    if (this.step4Title) this.step4Title.textContent = "Audit Result";
    if (this.step4Sub) this.step4Sub.textContent = "Preparing compliance report";

    // Request start: Step 1 active, others pending
    this.setStepState(0, "active");
    this.setStepState(1, "pending");
    this.setStepState(2, "pending");
    this.setStepState(3, "pending");

    // Real elapsed timer using performance.now() updated frequently so seconds flip immediately
    this.startTime = performance.now();
    if (this.timerEl) this.timerEl.textContent = "00:00";

    this.timerInterval = setInterval(() => {
      const elapsed = performance.now() - this.startTime;
      if (this.timerEl) {
        this.timerEl.textContent = this.formatTime(elapsed);
      }
    }, 200);

    // Subtle stage transition while request runs (DOES NOT claim backend completion)
    const t1 = setTimeout(() => {
      this.setStepState(0, "pending");
      this.setStepState(1, "active");
    }, 12000);
    this.stageTimeouts.push(t1);

    const t2 = setTimeout(() => {
      this.setStepState(1, "pending");
      this.setStepState(2, "active");
    }, 32000);
    this.stageTimeouts.push(t2);
  },

  complete(isCached = false) {
    this.stopTimers();
    if (!this.container) return;

    if (this.timerEl && this.startTime > 0) {
      const finalElapsed = performance.now() - this.startTime;
      this.timerEl.textContent = this.formatTime(finalElapsed);
    }

    // Actual HTTP response returned successfully: mark all completed
    for (let i = 0; i < 4; i++) {
      this.setStepState(i, "completed");
    }
    if (this.step4Title) this.step4Title.textContent = "Audit Result";
    if (this.step4Sub) this.step4Sub.textContent = "Compliance report ready";

    if (isCached && this.cachedBadge) {
      this.cachedBadge.style.display = "block";
    }
  },

  stopTimers() {
    if (this.timerInterval) {
      clearInterval(this.timerInterval);
      this.timerInterval = null;
    }
    this.stageTimeouts.forEach((tid) => clearTimeout(tid));
    this.stageTimeouts = [];
  },

  reset() {
    this.stopTimers();
    if (this.container) {
      this.container.style.display = "none";
    }
    for (let i = 0; i < 4; i++) {
      this.setStepState(i, "pending");
    }
    if (this.cachedBadge) {
      this.cachedBadge.style.display = "none";
    }
  },
};

// =============================================================================
// 3. PACKAGE IMAGE SCANNING FLOW: POST /api/scan
// =============================================================================
function setupPackageScanner() {
  const fileInput = document.getElementById("package-file-input");
  const fileNameDisplay = document.getElementById("package-file-name");
  const submitBtn = document.getElementById("btn-analyze-package");
  const scanForm = document.getElementById("package-scan-form");
  const statusEl = document.getElementById("package-scan-status");

  // Camera elements
  const openCameraBtn = document.getElementById("btn-open-camera");
  const cameraModal = document.getElementById("camera-modal");
  const cameraPreview = document.getElementById("camera-preview");
  const cameraCanvas = document.getElementById("camera-canvas");
  const cameraError = document.getElementById("camera-error");
  const cameraCaptureBtn = document.getElementById("btn-camera-capture");
  const cameraSwitchBtn = document.getElementById("btn-camera-switch");
  const cameraCancelBtn = document.getElementById("btn-camera-cancel");
  const cameraCloseX = document.getElementById("btn-camera-close-x");

  let activeStream = null;
  let currentFacingMode = "environment";
  let activeSelectedFile = null;

  if (!scanForm) return;

  function setSelectedFile(file) {
    activeSelectedFile = file;
    if (file) {
      fileNameDisplay.textContent = `${file.name} (${(file.size / 1024).toFixed(1)} KB)`;
      submitBtn.disabled = false;
    } else {
      fileNameDisplay.textContent = "No image selected";
      submitBtn.disabled = true;
    }
  }

  if (fileInput) {
    fileInput.addEventListener("change", () => {
      if (fileInput.files && fileInput.files[0]) {
        setSelectedFile(fileInput.files[0]);
      } else {
        setSelectedFile(null);
      }
    });
  }

  // --- CAMERA MANAGEMENT ---
  function stopCameraStream() {
    if (activeStream) {
      activeStream.getTracks().forEach((track) => {
        try {
          track.stop();
        } catch (e) {
          // Ignore track stop errors
        }
      });
      activeStream = null;
    }
    if (cameraPreview) {
      cameraPreview.srcObject = null;
    }
  }

  function closeCameraModal() {
    stopCameraStream();
    if (cameraModal) {
      cameraModal.style.display = "none";
    }
    if (cameraError) {
      cameraError.style.display = "none";
      cameraError.textContent = "";
    }
  }

  async function startCamera(facingMode = "environment") {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      if (cameraError) {
        cameraError.textContent = "Camera access is not supported by your browser or connection.";
        cameraError.style.display = "block";
      }
      return;
    }

    stopCameraStream();
    if (cameraError) {
      cameraError.style.display = "none";
    }

    try {
      const constraints = {
        video: {
          facingMode: { ideal: facingMode },
          width: { ideal: 1920 },
          height: { ideal: 1080 },
        },
        audio: false,
      };

      activeStream = await navigator.mediaDevices.getUserMedia(constraints);
      cameraPreview.srcObject = activeStream;
      currentFacingMode = facingMode;

      if (cameraSwitchBtn) {
        cameraSwitchBtn.style.display = "inline-block";
      }
    } catch (err) {
      console.warn("Camera access failed with ideal facing mode, falling back:", err);
      try {
        // Fallback without specific facingMode constraints
        activeStream = await navigator.mediaDevices.getUserMedia({ video: true, audio: false });
        cameraPreview.srcObject = activeStream;
      } catch (fallbackErr) {
        console.error("Camera acquisition error:", fallbackErr);
        if (cameraError) {
          cameraError.textContent = `Unable to access camera: ${fallbackErr.message || fallbackErr.name}. You can still use 'Choose Image' to upload.`;
          cameraError.style.display = "block";
        }
      }
    }
  }

  if (openCameraBtn && cameraModal) {
    openCameraBtn.addEventListener("click", () => {
      cameraModal.style.display = "flex";
      startCamera(currentFacingMode);
    });
  }

  if (cameraCloseX) cameraCloseX.addEventListener("click", closeCameraModal);
  if (cameraCancelBtn) cameraCancelBtn.addEventListener("click", closeCameraModal);

  if (cameraSwitchBtn) {
    cameraSwitchBtn.addEventListener("click", () => {
      const newMode = currentFacingMode === "environment" ? "user" : "environment";
      startCamera(newMode);
    });
  }

  if (cameraCaptureBtn && cameraCanvas && cameraPreview) {
    cameraCaptureBtn.addEventListener("click", () => {
      if (!cameraPreview.videoWidth || !cameraPreview.videoHeight) {
        alert("Camera preview is not active yet. Please wait a moment.");
        return;
      }

      cameraCanvas.width = cameraPreview.videoWidth;
      cameraCanvas.height = cameraPreview.videoHeight;
      const ctx = cameraCanvas.getContext("2d");
      ctx.drawImage(cameraPreview, 0, 0, cameraCanvas.width, cameraCanvas.height);

      cameraCanvas.toBlob(
        (blob) => {
          if (!blob) {
            alert("Failed to capture image frame from camera.");
            return;
          }
          const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
          const capturedFile = new File([blob], `camera_scan_${timestamp}.jpg`, {
            type: "image/jpeg",
          });
          setSelectedFile(capturedFile);
          closeCameraModal();
        },
        "image/jpeg",
        0.95
      );
    });
  }

  // --- SUBMISSION FLOW ---
  scanForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const file = activeSelectedFile || (fileInput && fileInput.files ? fileInput.files[0] : null);
    if (!file) return;

    const lowerName = file.name.toLowerCase();
    if (!lowerName.endsWith(".jpg") && !lowerName.endsWith(".jpeg") && file.type !== "image/jpeg") {
      analysisWorkflow.reset();
      setStatus(statusEl, "error", "Invalid file format. Only JPG/JPEG images are permitted.");
      return;
    }

    if (file.size > 10 * 1024 * 1024) {
      analysisWorkflow.reset();
      setStatus(statusEl, "error", "Payload too large (413): File exceeds the maximum allowed 10MB limit.");
      return;
    }

    submitBtn.disabled = true;
    statusEl.style.display = "none";

    // Start real elapsed timer and analysis workflow UI immediately before fetch
    analysisWorkflow.start();

    const formData = new FormData();
    formData.append("file", file);

    try {
      const res = await fetch(`${API_BASE_URL}/api/scan`, {
        method: "POST",
        body: formData,
      });

      if (!res.ok) {
        const errMsg = await parseHttpError(res);
        throw new Error(errMsg);
      }

      const data = await res.json();
      if (!data || !data.scan) {
        throw new Error("Malformed server response: Missing scan data payload.");
      }

      // Check if result was retrieved from cache
      const isCached = Boolean(data.cached || data.scan?.cached || data.analysis?.cached);
      analysisWorkflow.complete(isCached);

      // Brief transition (350ms) to allow the completion checkmarks to register cleanly
      setTimeout(() => {
        analysisWorkflow.reset();
        submitBtn.disabled = false;

        lastScanType = "package";
        renderPackageAuditResult(data.scan, data.analysis, file);
        showScreen("screen-audit-result");
      }, 350);
    } catch (err) {
      analysisWorkflow.reset();
      submitBtn.disabled = false;
      setStatus(statusEl, "error", `Inspection Failed: ${err.message}`);
    }
  });
}

// =============================================================================
// 4. PRODUCT URL SCANNING FLOW: POST /api/scan-url
// =============================================================================
function setupUrlScanner() {
  const urlForm = document.getElementById("url-scan-form");
  const urlInput = document.getElementById("product-url-input");
  const submitBtn = document.getElementById("btn-analyze-url");
  const statusEl = document.getElementById("url-scan-status");

  if (!urlForm || !urlInput) return;

  urlForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const url = urlInput.value.trim();

    if (!url.startsWith("http://") && !url.startsWith("https://")) {
      setStatus(statusEl, "error", "Invalid input: Please provide a valid HTTP or HTTPS product URL.");
      return;
    }

    submitBtn.disabled = true;
    setStatus(statusEl, "loading", "Fetching product listing and auditing Rule 6(10) declarations...");

    try {
      const res = await fetch(`${API_BASE_URL}/api/scan-url`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      });

      if (!res.ok) {
        const errMsg = await parseHttpError(res);
        throw new Error(errMsg);
      }

      const data = await res.json();
      if (data.status === "error" || (data.success === false && data.error)) {
        throw new Error(data.error || "Unable to fetch or analyze the product URL.");
      }

      statusEl.style.display = "none";
      submitBtn.disabled = false;

      lastScanType = "url";
      renderUrlAuditResult(data, url);
      showScreen("screen-audit-result");
    } catch (err) {
      submitBtn.disabled = false;
      setStatus(statusEl, "error", `URL Audit Error: ${err.message}`);
    }
  });
}

// Helper: Status Indicator
function setStatus(element, type, message) {
  if (!element) return;
  element.className = `scan-status-indicator ${type}`;
  element.textContent = message;
  element.style.display = "block";
}

// Helper: Human-readable HTTP Error parsing
async function parseHttpError(res) {
  let detail = "";
  try {
    const json = await res.json();
    if (json) {
      if (json.detail) {
        detail = typeof json.detail === "object" ? JSON.stringify(json.detail) : String(json.detail);
      } else if (json.error) {
        detail = String(json.error);
      }
    }
  } catch (_) {
    // Non-JSON response body
  }

  if (detail) return detail;

  switch (res.status) {
    case 400:
      return "Bad Request (400): The submitted file or parameters are invalid.";
    case 404:
      return "Not Found (404): The requested inspection record or resource does not exist.";
    case 413:
      return "Payload Too Large (413): The uploaded file exceeds the statutory file size limit.";
    case 422:
      return "Unprocessable Entity (422): The image or URL could not be processed by the inspection engine.";
    case 500:
      return "Internal Server Error (500): The inspection service encountered an unexpected error.";
    default:
      return `Server returned error (${res.status} ${res.statusText || ""}).`.trim();
  }
}

// =============================================================================
// 5. AUDIT RESULT RENDERER (OFFICIAL REGULATORY INSPECTION REPORT)
// =============================================================================

/**
 * Render physical package inspection result directly from backend payload
 */
function renderPackageAuditResult(scan, analysis, localFile = null) {
  activeScanId = scan?.id || null;

  // Header metadata directly from backend
  document.getElementById("audit-product-name").textContent = scan?.filename || "Physical Package Label";
  document.getElementById("audit-scan-id").textContent = scan?.id || "—";
  document.getElementById("audit-date-time").textContent = scan?.created_at
    ? scan.created_at.substring(0, 19).replace("T", " ")
    : new Date().toISOString().substring(0, 19).replace("T", " ");

  const rawScore = analysis?.compliance?.score ?? scan?.compliance_score;
  const scoreText = typeof rawScore === "number" ? `${rawScore.toFixed(2)}%` : "—";
  document.getElementById("audit-score-display").textContent = scoreText;

  // Audit Verdict Badge directly from backend status
  const statusRaw = String(analysis?.compliance?.status ?? scan?.compliance_status ?? "COMPLIANT").toUpperCase();
  const verdictWrapper = document.getElementById("audit-verdict-badge-wrapper");

  if (statusRaw === "COMPLIANT") {
    verdictWrapper.innerHTML = `<span class="verdict-badge verdict-pass">PASS — COMPLIANT</span>`;
  } else if (statusRaw === "WARNING" || statusRaw === "PARTIALLY_COMPLIANT" || statusRaw === "REVIEW_REQUIRED") {
    verdictWrapper.innerHTML = `<span class="verdict-badge verdict-warn">WARNING — REVIEW REQUIRED</span>`;
  } else {
    verdictWrapper.innerHTML = `<span class="verdict-badge verdict-fail">FAIL — NON-COMPLIANT</span>`;
  }

  // PDF Report Download Button visibility
  const pdfBtn = document.getElementById("btn-download-pdf");
  if (activeScanId) {
    pdfBtn.style.display = "inline-flex";
    pdfBtn.disabled = false;
  } else {
    pdfBtn.style.display = "none";
  }

  // Mandatory Declarations Checklist Table
  const checklistTbody = document.getElementById("audit-checklist-tbody");
  checklistTbody.innerHTML = "";

  const declarations = analysis?.declarations || scan?.declarations || {};
  const fields = analysis?.fields || scan?.fields || {};
  const merged = { ...declarations, ...fields };

  PACKAGE_RULE_DEFINITIONS.forEach((rule) => {
    const item = merged[rule.key];
    let detectedText = "NOT DETECTED";
    let isPresent = false;
    let isWarning = false;

    if (item && typeof item === "object") {
      const itemStatus = String(item.status || "FOUND").toUpperCase();
      if (item.value !== null && item.value !== undefined && item.value !== "") {
        detectedText = typeof item.value === "object" ? formatStructuredValue(item.value) : String(item.value);
        isPresent = (itemStatus === "FOUND" || itemStatus === "UNCERTAIN");
      }
      if (itemStatus === "UNCERTAIN") {
        isWarning = true;
      }
    } else if (item !== null && item !== undefined && String(item).trim() !== "") {
      detectedText = String(item);
      isPresent = true;
    }

    let statusBadgeHtml = `<span class="status-badge badge-fail">FAIL</span>`;
    if (isPresent) {
      statusBadgeHtml = isWarning
        ? `<span class="status-badge badge-warn">WARNING</span>`
        : `<span class="status-badge badge-pass">PASS</span>`;
    }

    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${statusBadgeHtml}</td>
      <td><strong>${escapeHtml(rule.label)}</strong></td>
      <td><code>${escapeHtml(detectedText)}</code></td>
      <td>${escapeHtml(rule.clause)}</td>
    `;
    checklistTbody.appendChild(tr);
  });

  // Violations Block (only rendered when violations exist)
  const violations = analysis?.compliance?.violations || scan?.violations || [];
  const violationsContainer = document.getElementById("audit-violations-container");
  const violationsTbody = document.getElementById("audit-violations-tbody");

  if (violations && violations.length > 0) {
    violationsContainer.style.display = "block";
    violationsTbody.innerHTML = "";

    violations.forEach((v) => {
      const severity = String(v.severity || "HIGH").toUpperCase();
      const sevBadge = (severity === "MEDIUM" || severity === "LOW" || severity === "WARNING")
        ? `<span class="status-badge badge-warn">WARNING</span>`
        : `<span class="status-badge badge-fail">FAIL</span>`;

      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong class="table-code">${escapeHtml(v.rule_code || "LM-RULE")}</strong></td>
        <td>${sevBadge}</td>
        <td>${escapeHtml(v.description || "Mandatory declaration missing or inconsistent.")}</td>
        <td>${escapeHtml(v.clause || "PCR 2011")}</td>
      `;
      violationsTbody.appendChild(tr);
    });
  } else {
    violationsContainer.style.display = "none";
  }

  // Evidence Image Block
  const evidenceContainer = document.getElementById("audit-evidence-container");
  const evidenceImg = document.getElementById("audit-evidence-img");

  if (localFile) {
    evidenceImg.src = URL.createObjectURL(localFile);
    evidenceContainer.style.display = "block";
  } else if (scan?.image_url) {
    evidenceImg.src = scan.image_url;
    evidenceContainer.style.display = "block";
  } else {
    evidenceContainer.style.display = "none";
  }
}

/**
 * Render e-commerce URL inspection result directly from backend response
 */
function renderUrlAuditResult(result, targetUrl) {
  activeScanId = null;

  // Header metadata
  document.getElementById("audit-product-name").textContent = result.product_title || targetUrl;
  document.getElementById("audit-scan-id").textContent = result.final_url ? "DIGITAL-URL" : "E-COM-AUDIT";
  document.getElementById("audit-date-time").textContent = new Date().toISOString().substring(0, 19).replace("T", " ");

  const rawScore = result.compliance_score;
  const scoreText = typeof rawScore === "number" ? `${rawScore.toFixed(2)}%` : "—";
  document.getElementById("audit-score-display").textContent = scoreText;

  // Verdict Badge directly from backend compliance_status
  const statusRaw = String(result.compliance_status || "NON_COMPLIANT").toUpperCase();
  const verdictWrapper = document.getElementById("audit-verdict-badge-wrapper");

  if (statusRaw === "COMPLIANT") {
    verdictWrapper.innerHTML = `<span class="verdict-badge verdict-pass">PASS — COMPLIANT</span>`;
  } else if (statusRaw === "PARTIALLY_COMPLIANT" || statusRaw === "REVIEW_REQUIRED" || statusRaw === "WARNING") {
    verdictWrapper.innerHTML = `<span class="verdict-badge verdict-warn">WARNING — REVIEW REQUIRED</span>`;
  } else {
    verdictWrapper.innerHTML = `<span class="verdict-badge verdict-fail">FAIL — NON-COMPLIANT</span>`;
  }

  // Hide PDF button for digital scans
  document.getElementById("btn-download-pdf").style.display = "none";
  document.getElementById("audit-evidence-container").style.display = "none";

  // Checklist Table
  const checklistTbody = document.getElementById("audit-checklist-tbody");
  checklistTbody.innerHTML = "";

  const auditFields = result.mandatory_fields_audit || {};
  const scrapedMeta = result.scraped_metadata || {};

  ECOM_RULE_DEFINITIONS.forEach((rule) => {
    const auditItem = auditFields[rule.key] || {};
    const webVal = auditItem.web_value !== undefined ? auditItem.web_value : scrapedMeta[rule.key];
    const isFound = auditItem.status === "FOUND" || (webVal !== null && webVal !== undefined && webVal !== "");

    let detectedText = "NOT DECLARED";
    if (webVal !== null && webVal !== undefined && webVal !== "") {
      detectedText = typeof webVal === "object" ? formatStructuredValue(webVal) : String(webVal);
    }

    const statusBadgeHtml = isFound
      ? `<span class="status-badge badge-pass">PASS</span>`
      : `<span class="status-badge badge-fail">FAIL</span>`;

    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${statusBadgeHtml}</td>
      <td><strong>${escapeHtml(rule.label)}</strong></td>
      <td><code>${escapeHtml(detectedText)}</code></td>
      <td>${escapeHtml(rule.clause)}</td>
    `;
    checklistTbody.appendChild(tr);
  });

  // Violations & Discrepancies
  const discrepancies = result.discrepancies || [];
  const missing = result.missing_declarations || [];
  const violationsContainer = document.getElementById("audit-violations-container");
  const violationsTbody = document.getElementById("audit-violations-tbody");

  if (discrepancies.length > 0 || missing.length > 0) {
    violationsContainer.style.display = "block";
    violationsTbody.innerHTML = "";

    // Render Discrepancies
    discrepancies.forEach((d) => {
      const severity = String(d.severity || "HIGH").toUpperCase();
      const sevBadge = (severity === "CRITICAL" || severity === "HIGH")
        ? `<span class="status-badge badge-fail">FAIL</span>`
        : `<span class="status-badge badge-warn">WARNING</span>`;

      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong class="table-code">${escapeHtml(d.field ? d.field.toUpperCase() : "MISMATCH")}</strong></td>
        <td>${sevBadge}</td>
        <td>Listing: <em>${escapeHtml(String(d.web_listing_value || "—"))}</em> vs Packaging: <em>${escapeHtml(String(d.packaging_label_value || "—"))}</em></td>
        <td>${escapeHtml(d.rule || "Rule 6(10) PCR 2011")}</td>
      `;
      violationsTbody.appendChild(tr);
    });

    // Render Missing Mandatory Fields
    missing.forEach((mField) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong class="table-code">${escapeHtml(mField.toUpperCase())}</strong></td>
        <td><span class="status-badge badge-fail">FAIL</span></td>
        <td>Mandatory statutory declaration is absent from the product listing page.</td>
        <td>Rule 6(10) PCR 2011</td>
      `;
      violationsTbody.appendChild(tr);
    });
  } else {
    violationsContainer.style.display = "none";
  }
}

// Structured value formatting utility
function formatStructuredValue(val) {
  if (!val) return "NOT DETECTED";
  if (typeof val !== "object") return String(val);
  const parts = [];
  if (val.phone) parts.push(`Tel: ${val.phone}`);
  if (val.email) parts.push(`Email: ${val.email}`);
  if (val.address) parts.push(`Addr: ${val.address}`);
  return parts.length > 0 ? parts.join(" | ") : JSON.stringify(val);
}

// XSS Prevention Utility
function escapeHtml(str) {
  if (str === null || str === undefined) return "";
  return String(str).replace(/[&<>"']/g, (c) => {
    return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
  });
}

// =============================================================================
// 6. PDF REPORT DOWNLOAD HANDLER
// =============================================================================
function setupPdfReportDownload() {
  const btn = document.getElementById("btn-download-pdf");
  if (!btn) return;

  btn.addEventListener("click", async () => {
    if (!activeScanId) {
      alert("No physical package scan selected for PDF download.");
      return;
    }

    try {
      btn.disabled = true;
      btn.textContent = "Generating PDF...";

      // Backend route is POST /api/reports/pdf?scan_id=... with fallback to GET if 405
      let res = await fetch(`${API_BASE_URL}/api/reports/pdf?scan_id=${encodeURIComponent(activeScanId)}`, {
        method: "POST",
      });

      if (res.status === 405) {
        res = await fetch(`${API_BASE_URL}/api/reports/pdf?scan_id=${encodeURIComponent(activeScanId)}`, {
          method: "GET",
        });
      }

      if (!res.ok) {
        const errMsg = await parseHttpError(res);
        throw new Error(errMsg);
      }

      const blob = await res.blob();
      const blobUrl = window.URL.createObjectURL(blob);
      const tempLink = document.createElement("a");
      tempLink.href = blobUrl;
      tempLink.download = `packsure-audit-${activeScanId}.pdf`;
      document.body.appendChild(tempLink);
      tempLink.click();
      tempLink.remove();
      window.URL.revokeObjectURL(blobUrl);

      btn.disabled = false;
      btn.textContent = "Download PDF Report";
    } catch (err) {
      btn.disabled = false;
      btn.textContent = "Download PDF Report";
      alert(`PDF Download Error: ${err.message}`);
    }
  });
}
