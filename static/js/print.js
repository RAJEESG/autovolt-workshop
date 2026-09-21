/**
 * AutoVolt Pro - Print Formatting Controller
 * Handles A4 Tax Invoice, 80mm POS Thermal Receipt, and Barcode Sticker printing.
 */

window.printA4Invoice = function(invoiceId) {
    const printWindow = window.open(`/invoice/${invoiceId}/print?format=a4`, '_blank');
    if (printWindow) {
        printWindow.focus();
    }
};

window.printThermalReceipt = function(invoiceId) {
    const printWindow = window.open(`/invoice/${invoiceId}/print?format=thermal`, '_blank');
    if (printWindow) {
        printWindow.focus();
    }
};

window.printBarcodeStickers = function() {
    window.print();
};
