/**
 * AutoVolt Barcode POS & Hardware Scanner Engine
 * Automatically detects rapid keystrokes from USB/Bluetooth Gun Scanners
 * and provides camera-based HTML5 scanning support.
 */

class BarcodeScannerManager {
    constructor() {
        this.barcodeBuffer = "";
        this.lastKeyTime = 0;
        this.scanThresholdMs = 50; // Hardware scanners type keys within 20-50ms
        this.audioContext = null;
        this.onScanCallback = null;
        
        this.initHardwareScannerListener();
    }

    // Play pleasant high-pitch audio beep on successful barcode scan
    playBeepSound(success = true) {
        try {
            if (!this.audioContext) {
                this.audioContext = new (window.AudioContext || window.webkitAudioContext)();
            }
            const osc = this.audioContext.createOscillator();
            const gain = this.audioContext.createGain();
            osc.connect(gain);
            gain.connect(this.audioContext.destination);
            
            if (success) {
                osc.type = "sine";
                osc.frequency.setValueAtTime(1400, this.audioContext.currentTime);
                gain.gain.setValueAtTime(0.15, this.audioContext.currentTime);
                gain.gain.exponentialRampToValueAtTime(0.01, this.audioContext.currentTime + 0.12);
                osc.start();
                osc.stop(this.audioContext.currentTime + 0.12);
            } else {
                osc.type = "sawtooth";
                osc.frequency.setValueAtTime(300, this.audioContext.currentTime);
                gain.gain.setValueAtTime(0.2, this.audioContext.currentTime);
                gain.gain.exponentialRampToValueAtTime(0.01, this.audioContext.currentTime + 0.25);
                osc.start();
                osc.stop(this.audioContext.currentTime + 0.25);
            }
        } catch (e) {
            console.warn("Audio Context beep error:", e);
        }
    }

    // Global listener for USB/Bluetooth barcode gun scanners
    initHardwareScannerListener() {
        document.addEventListener("keydown", (e) => {
            const currentTime = new Date().getTime();
            const timeDiff = currentTime - this.lastKeyTime;
            
            // Check if user is typing in a regular text input or textarea
            const targetTag = e.target.tagName.toLowerCase();
            const isManualInputField = (targetTag === "input" || targetTag === "textarea") && !e.target.classList.contains("barcode-scanner-target");

            if (e.key === "Enter") {
                if (this.barcodeBuffer.length >= 4) {
                    // Barcode scan completed!
                    const scannedCode = this.barcodeBuffer.trim();
                    this.barcodeBuffer = "";
                    this.triggerScan(scannedCode);
                    if (!isManualInputField) {
                        e.preventDefault();
                    }
                } else if (e.target.classList.contains("barcode-input-field")) {
                    const manualVal = e.target.value.trim();
                    if (manualVal) {
                        this.triggerScan(manualVal);
                        e.target.value = "";
                        e.preventDefault();
                    }
                }
            } else if (e.key.length === 1) {
                // If keys arrive in super-fast bursts (< 60ms between keys), it is a barcode scanner
                if (timeDiff > this.scanThresholdMs && this.barcodeBuffer.length > 0) {
                    this.barcodeBuffer = ""; // Reset if too slow
                }
                this.barcodeBuffer += e.key;
            }
            this.lastKeyTime = currentTime;
        });
    }

    // Set callback for when barcode is detected
    setScanCallback(callback) {
        this.onScanCallback = callback;
    }

    // Trigger item lookup & callback
    async triggerScan(barcode) {
        console.log(`[Barcode Scanned] => ${barcode}`);
        try {
            const response = await fetch(`/api/inventory/scan/${encodeURIComponent(barcode)}`);
            if (response.ok) {
                const item = await response.json();
                this.playBeepSound(true);
                if (window.showToast) {
                    window.showToast(`📦 Scanned: ${item.part_name} (₹${item.selling_price})`, "success");
                }
                if (this.onScanCallback) {
                    this.onScanCallback(item);
                }
            } else {
                this.playBeepSound(false);
                if (window.showToast) {
                    window.showToast(`⚠️ No item found for barcode: ${barcode}`, "warning");
                }
            }
        } catch (err) {
            console.error("Scan lookup error:", err);
            this.playBeepSound(false);
        }
    }
}

// Global instance
window.barcodeScanner = new BarcodeScannerManager();
