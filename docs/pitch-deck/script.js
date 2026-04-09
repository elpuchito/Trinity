document.addEventListener('DOMContentLoaded', () => {
    const slides = document.querySelectorAll('.slide');
    const btnNext = document.getElementById('btn-next');
    const btnPrev = document.getElementById('btn-prev');
    const counter = document.getElementById('slide-counter');
    
    let currentSlide = 0;
    const totalSlides = slides.length;

    function updateSlide() {
        // Update visibility
        slides.forEach((slide, index) => {
            if (index === currentSlide) {
                slide.classList.add('active');
            } else {
                slide.classList.remove('active');
            }
        });

        // Update counter
        counter.textContent = `${currentSlide + 1} / ${totalSlides}`;
        
        // Disable buttons if at start/end
        btnPrev.style.opacity = currentSlide === 0 ? '0.3' : '1';
        btnPrev.style.cursor = currentSlide === 0 ? 'default' : 'pointer';
        
        btnNext.style.opacity = currentSlide === totalSlides - 1 ? '0.3' : '1';
        btnNext.style.cursor = currentSlide === totalSlides - 1 ? 'default' : 'pointer';
    }

    function goToNext() {
        if (currentSlide < totalSlides - 1) {
            currentSlide++;
            updateSlide();
        }
    }

    function goToPrev() {
        if (currentSlide > 0) {
            currentSlide--;
            updateSlide();
        }
    }

    // Event Listeners
    btnNext.addEventListener('click', () => {
        if (currentSlide < totalSlides - 1) goToNext();
    });

    btnPrev.addEventListener('click', () => {
        if (currentSlide > 0) goToPrev();
    });

    // Keyboard navigation
    document.addEventListener('keydown', (e) => {
        if (e.key === 'ArrowRight' || e.key === ' ') {
            goToNext();
        } else if (e.key === 'ArrowLeft') {
            goToPrev();
        }
    });

    // Initial setup
    updateSlide();
});
