// Client-side JavaScript for enhanced functionality
document.addEventListener('DOMContentLoaded', function() {
    // Auto-calculate equal shares when amount changes
    const amountInput = document.getElementById('amount');
    if (amountInput) {
        amountInput.addEventListener('input', function() {
            const shareInputs = document.querySelectorAll('.share-input');
            const totalMembers = shareInputs.length;
            const amount = parseFloat(this.value) || 0;
            const share = amount / totalMembers;
            
            shareInputs.forEach(input => {
                input.value = share.toFixed(2);
            });
        });
    }
});