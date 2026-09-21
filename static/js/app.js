/**
 * AutoVolt Pro - Main UI Controller & Interactivity
 */

// Toast notification system
window.showToast = function(message, type = "info") {
    let container = document.getElementById("toast-container");
    if (!container) {
        container = document.createElement("div");
        container.id = "toast-container";
        container.className = "toast-container";
        document.body.appendChild(container);
    }
    
    const colors = {
        success: "bg-emerald-600 text-white border-emerald-700",
        error: "bg-rose-600 text-white border-rose-700",
        warning: "bg-amber-600 text-white border-amber-700",
        info: "bg-blue-600 text-white border-blue-700"
    };
    
    const toast = document.createElement("div");
    toast.className = `toast flex items-center gap-3 px-4 py-3 rounded-xl shadow-xl border text-sm font-medium ${colors[type] || colors.info}`;
    toast.innerHTML = `
        <span>${message}</span>
        <button onclick="this.parentElement.remove()" class="ml-auto opacity-70 hover:opacity-100">✕</button>
    `;
    container.appendChild(toast);
    
    setTimeout(() => {
        if (toast.parentElement) {
            toast.style.transition = "all 0.4s ease";
            toast.style.opacity = "0";
            toast.style.transform = "translateX(100%)";
            setTimeout(() => toast.remove(), 400);
        }
    }, 4000);
};

// Open and Close Modal Helpers
window.openModal = function(modalId) {
    const el = document.getElementById(modalId);
    if (el) {
        el.classList.remove("hidden");
        el.classList.add("flex");
    }
};

window.closeModal = function(modalId) {
    const el = document.getElementById(modalId);
    if (el) {
        el.classList.add("hidden");
        el.classList.remove("flex");
    }
};

// 1-Click WhatsApp Share Trigger
window.shareWhatsApp = function(url) {
    window.open(url, "_blank", "noopener,noreferrer");
};

// Copy text to clipboard helper
window.copyToClipboard = function(text, successMsg = "Copied to clipboard!") {
    navigator.clipboard.writeText(text).then(() => {
        window.showToast(successMsg, "success");
    }).catch(err => {
        window.showToast("Failed to copy", "error");
    });
};
