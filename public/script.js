/*
 * V.I.T.A. - "Salva in PDF"
 * Once a chat has its summary report, a button is shown after the last message: it downloads the whole
 * conversation as a PDF, written by the app itself (see scripts/chat_pdf.py).
 */
(function () {
    const BUTTON_ID = "vita-pdf";
    const REPORT = '[data-step-type="assistant_message"] img[src*="/avatars/Primario"]';
    const THREAD = /^\/thread\/([0-9a-f-]+)/i;

    function createButton() {
        const button = document.createElement("button");
        button.id = BUTTON_ID;
        button.type = "button";
        button.textContent = "Salva in PDF";
        button.title = "Scarica tutta la conversazione in PDF";
        button.addEventListener("click", () => {
            const thread = THREAD.exec(window.location.pathname);
            if (thread) window.location.assign("/vita/pdf/" + thread[1]);
        });
        return button;
    }

    // Keeps the button as the last element of the chat, and only in a chat that has its report.
    function placeButton() {
        const existing = document.getElementById(BUTTON_ID);
        const report = document.querySelector(REPORT);
        const step = report && report.closest(".step");
        if (!step || !step.parentElement || !THREAD.test(window.location.pathname)) {
            if (existing) existing.remove();
            return;
        }
        const messages = step.parentElement;
        const button = existing || createButton();
        if (messages.lastElementChild !== button) messages.appendChild(button);
    }

    let scheduled = false;
    new MutationObserver(() => {
        if (scheduled) return;
        scheduled = true;
        requestAnimationFrame(() => {
            scheduled = false;
            placeButton();
        });
    }).observe(document.documentElement, { childList: true, subtree: true });
})();
