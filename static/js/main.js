document.addEventListener('DOMContentLoaded', function() {
    const tributeForm = document.querySelector('form[method="post"]');
    
    if (tributeForm) {
        tributeForm.addEventListener('submit', function(e) {
            const submitBtn = this.querySelector('button[type="submit"], input[type="submit"]');
            
            if (submitBtn) {
                // Disable button to prevent double-submit
                submitBtn.disabled = true;
                
                // Store original text
                const originalText = submitBtn.textContent || submitBtn.value;
                
                // Show loading state with Bootstrap spinner
                if (submitBtn.tagName === 'BUTTON') {
                    submitBtn.innerHTML = `
                        <span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>
                        Processing...
                    `;
                } else {
                    submitBtn.value = 'Processing...';
                }
                
                // Re-enable after 10 seconds as fallback
                setTimeout(function() {
                    submitBtn.disabled = false;
                    if (submitBtn.tagName === 'BUTTON') {
                        submitBtn.textContent = originalText;
                    } else {
                        submitBtn.value = originalText;
                    }
                }, 10000);
            }
        });
    }
});
