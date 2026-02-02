// Pflegeplanung - Main JavaScript

document.addEventListener('DOMContentLoaded', function() {
    // Initialize tooltips
    var tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // Initialize popovers
    var popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
    popoverTriggerList.map(function (popoverTriggerEl) {
        return new bootstrap.Popover(popoverTriggerEl);
    });

    // Auto-hide alerts after 5 seconds
    setTimeout(function() {
        var alerts = document.querySelectorAll('.alert:not(.alert-permanent)');
        alerts.forEach(function(alert) {
            var bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
            bsAlert.close();
        });
    }, 5000);
});

// Confirm delete actions
function confirmDelete(message) {
    return confirm(message || 'Möchten Sie diesen Eintrag wirklich löschen?');
}

// Show loading overlay
function showLoading() {
    var overlay = document.createElement('div');
    overlay.className = 'loading-overlay';
    overlay.id = 'loading-overlay';
    overlay.innerHTML = `
        <div class="text-center">
            <div class="spinner-border text-primary" role="status" style="width: 3rem; height: 3rem;">
                <span class="visually-hidden">Laden...</span>
            </div>
            <div class="mt-2">Bitte warten...</div>
        </div>
    `;
    document.body.appendChild(overlay);
}

// Hide loading overlay
function hideLoading() {
    var overlay = document.getElementById('loading-overlay');
    if (overlay) {
        overlay.remove();
    }
}

// Format date for display
function formatDate(dateString) {
    var date = new Date(dateString);
    return date.toLocaleDateString('de-DE', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric'
    });
}

// AJAX helper function
async function fetchJSON(url, options = {}) {
    const defaultOptions = {
        headers: {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
    };

    const mergedOptions = { ...defaultOptions, ...options };

    if (options.body && typeof options.body === 'object') {
        mergedOptions.body = JSON.stringify(options.body);
    }

    try {
        const response = await fetch(url, mergedOptions);
        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.error || 'Ein Fehler ist aufgetreten');
        }

        return data;
    } catch (error) {
        console.error('Fetch error:', error);
        throw error;
    }
}

// Dienstplan cell click handler
function handleDienstplanClick(cell) {
    const mitarbeiterId = cell.dataset.mitarbeiterId;
    const datum = cell.dataset.datum;
    const dienstId = cell.dataset.dienstId;

    // Open modal or perform action
    if (typeof openDienstplanModal === 'function') {
        openDienstplanModal(mitarbeiterId, datum, dienstId);
    }
}

// Color picker initialization
function initColorPicker(inputId) {
    const input = document.getElementById(inputId);
    if (input) {
        input.addEventListener('input', function() {
            const preview = document.getElementById(inputId + '-preview');
            if (preview) {
                preview.style.backgroundColor = this.value;
            }
        });
    }
}

// Dynamic form field handling for rules
function updateRegelParameter(regelTyp) {
    const parameterContainer = document.getElementById('parameter-container');
    if (!parameterContainer) return;

    // Clear existing fields
    parameterContainer.innerHTML = '';

    // Add fields based on rule type
    const parameterDefinitions = window.regelTypParameter || {};
    const params = parameterDefinitions[regelTyp] || {};

    for (const [key, config] of Object.entries(params)) {
        const div = document.createElement('div');
        div.className = 'mb-3';

        let inputHtml = '';
        switch (config.typ) {
            case 'integer':
                inputHtml = `<input type="number" class="form-control" name="param_${key}"
                            id="param_${key}" value="${config.default || ''}" required>`;
                break;
            case 'date':
                inputHtml = `<input type="date" class="form-control" name="param_${key}"
                            id="param_${key}" required>`;
                break;
            case 'dienst':
                inputHtml = `<select class="form-select" name="param_${key}" id="param_${key}" required>
                            <option value="">Bitte wählen...</option>
                            </select>`;
                break;
            case 'qualifikation':
                inputHtml = `<select class="form-select" name="param_${key}" id="param_${key}" required>
                            <option value="">Bitte wählen...</option>
                            </select>`;
                break;
        }

        div.innerHTML = `
            <label for="param_${key}" class="form-label">${config.label}</label>
            ${inputHtml}
        `;

        parameterContainer.appendChild(div);

        // Load options for select fields
        if (config.typ === 'dienst') {
            loadDiensteOptions(`param_${key}`);
        } else if (config.typ === 'qualifikation') {
            loadQualifikationenOptions(`param_${key}`);
        }
    }
}

// Load Dienste options
async function loadDiensteOptions(selectId) {
    try {
        const data = await fetchJSON('/dienste/api/list');
        const select = document.getElementById(selectId);
        if (select && data.dienste) {
            data.dienste.forEach(dienst => {
                const option = document.createElement('option');
                option.value = dienst.id;
                option.textContent = dienst.name;
                select.appendChild(option);
            });
        }
    } catch (error) {
        console.error('Error loading dienste:', error);
    }
}

// Load Qualifikationen options
async function loadQualifikationenOptions(selectId) {
    try {
        const data = await fetchJSON('/qualifikationen/api/list');
        const select = document.getElementById(selectId);
        if (select && data.qualifikationen) {
            data.qualifikationen.forEach(qual => {
                const option = document.createElement('option');
                option.value = qual.id;
                option.textContent = qual.name;
                select.appendChild(option);
            });
        }
    } catch (error) {
        console.error('Error loading qualifikationen:', error);
    }
}
