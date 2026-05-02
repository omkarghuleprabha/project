/* ==================== AUTO-DISMISS NOTIFICATIONS ==================== */

document.addEventListener('DOMContentLoaded', function() {
    // Initialize all notifications with auto-dismiss
    const alerts = document.querySelectorAll('.alert');
    
    alerts.forEach(alert => {
        // Set a timeout to auto-dismiss after 4 seconds
        setTimeout(function() {
            dismissAlert(alert);
        }, 4000);
        
        // Add click handler for manual close button
        const closeBtn = alert.querySelector('.btn-close');
        if (closeBtn) {
            closeBtn.addEventListener('click', function(e) {
                e.preventDefault();
                dismissAlert(alert);
            });
        }
    });
});

/**
 * Dismiss alert with slide-out animation
 * @param {Element} alert - The alert element to dismiss
 */
function dismissAlert(alert) {
    // Add class to trigger slide-out animation
    alert.classList.add('alert-removing');
    
    // Remove element from DOM after animation completes
    setTimeout(function() {
        alert.remove();
    }, 400);
}

/* ==================== UTILITY FUNCTIONS ==================== */

/**
 * Show a flash message programmatically
 * @param {string} message - The message to display
 * @param {string} category - Category: 'success', 'danger', 'warning', 'info'
 * @param {number} duration - Duration in milliseconds (default: 4000)
 */
function showFlashMessage(message, category = 'info', duration = 4000) {
    const flashShell = document.querySelector('.flash-shell');
    
    // Create flash shell if it doesn't exist
    let shell = flashShell;
    if (!shell) {
        shell = document.createElement('div');
        shell.className = 'flash-shell';
        document.body.appendChild(shell);
    }
    
    // Create alert element
    const alert = document.createElement('div');
    alert.className = `alert alert-${category} alert-dismissible fade show`;
    alert.setAttribute('role', 'alert');
    alert.innerHTML = `
        ${message}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    
    // Add to shell
    shell.appendChild(alert);
    
    // Trigger animation
    setTimeout(() => {
        alert.style.animation = 'slideInRight 0.4s ease-out';
    }, 10);
    
    // Auto-dismiss
    setTimeout(function() {
        dismissAlert(alert);
    }, duration);
    
    // Manual close button
    const closeBtn = alert.querySelector('.btn-close');
    if (closeBtn) {
        closeBtn.addEventListener('click', function(e) {
            e.preventDefault();
            dismissAlert(alert);
        });
    }
}

/* ==================== EXAMPLE USAGE ==================== */
// showFlashMessage('This is a success message!', 'success');
// showFlashMessage('This is an error message!', 'danger');
// showFlashMessage('This is a warning message!', 'warning');
// showFlashMessage('This is an info message!', 'info');