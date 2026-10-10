function setReactInputValue(input, value) {
    const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
    nativeInputValueSetter.call(input, value);
    const event = new Event('input', { bubbles: true });
    input.dispatchEvent(event);
}

// --------------------------------------------------------
// 1. Modal Component for Guest Restriction
// --------------------------------------------------------
function showGuestModal() {
    if (document.getElementById('guest-modal')) return;

    const overlay = document.createElement('div');
    overlay.id = 'guest-modal';
    overlay.style.cssText = 'position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; background: rgba(0,0,0,0.7); z-index: 9999; display: flex; justify-content: center; align-items: center; font-family: system-ui, -apple-system, sans-serif;';

    const modal = document.createElement('div');
    modal.style.cssText = 'background: #212121; width: 400px; border-radius: 16px; padding: 24px; position: relative; color: white; box-shadow: 0 10px 30px rgba(0,0,0,0.5); text-align: center;';

    const closeBtn = document.createElement('div');
    closeBtn.innerHTML = '&times;';
    closeBtn.style.cssText = 'position: absolute; top: 16px; right: 20px; font-size: 24px; cursor: pointer; color: #aaa;';
    closeBtn.onclick = () => overlay.remove();

    const title = document.createElement('h2');
    title.innerText = 'Log in or sign up';
    title.style.cssText = 'margin: 10px 0 20px 0; font-size: 24px; font-weight: 500;';

    const desc = document.createElement('p');
    desc.innerText = "You'll get smarter responses and can upload files, images, and more.";
    desc.style.cssText = 'color: #ccc; font-size: 15px; margin-bottom: 30px; line-height: 1.5;';

    const loginBtn = document.createElement('button');
    loginBtn.innerText = 'Log in with Email';
    loginBtn.style.cssText = 'width: 100%; padding: 12px; background: white; color: black; border: none; border-radius: 24px; font-size: 16px; font-weight: 600; cursor: pointer;';
    loginBtn.onclick = () => {
        // Clear tokens and explicitly redirect to login
        localStorage.clear();
        sessionStorage.clear();
        document.cookie = "token=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;";
        document.cookie = "chainlit-token=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;";
        
        // Push user back to home/login and hard refresh
        window.location.href = '/login';
        setTimeout(() => window.location.reload(true), 100);
    };

    modal.appendChild(closeBtn);
    modal.appendChild(title);
    modal.appendChild(desc);
    modal.appendChild(loginBtn);
    overlay.appendChild(modal);
    document.body.appendChild(overlay);
}

// --------------------------------------------------------
// 2. Web Speech API (Voice to Text) Mic Button
// --------------------------------------------------------
let recognition = null;
if ('webkitSpeechRecognition' in window) {
    recognition = new webkitSpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.lang = 'en-US'; // You can change to 'hi-IN' if needed
}

function injectMicButton() {
    const chatInput = document.getElementById('chat-input') || document.querySelector('textarea');
    if (!chatInput || document.getElementById('custom-mic-btn')) return;

    const micBtn = document.createElement('button');
    micBtn.id = 'custom-mic-btn';
    // Microphone SVG icon
    micBtn.innerHTML = '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z"></path><path d="M19 10v2a7 7 0 0 1-14 0v-2"></path><line x1="12" y1="19" x2="12" y2="22"></line></svg>';
    micBtn.style.cssText = 'background: transparent; border: none; color: #888; cursor: pointer; padding: 8px; margin-right: 5px; transition: color 0.2s; display: flex; align-items: center; justify-content: center;';
    
    // Find the submit button or a good place to put the mic
    const submitBtn = document.getElementById('step-submit-button') || document.getElementById('ask-button') || (chatInput.parentElement && chatInput.parentElement.querySelector('button'));
    
    if (submitBtn && submitBtn.parentNode) {
        submitBtn.parentNode.style.display = 'flex';
        submitBtn.parentNode.style.alignItems = 'center';
        submitBtn.parentNode.insertBefore(micBtn, submitBtn);
    } else {
        const wrapper = chatInput.parentElement;
        if(wrapper) {
            wrapper.style.display = 'flex';
            wrapper.appendChild(micBtn);
        }
    }

    if (!recognition) {
        micBtn.onclick = (e) => {
            e.preventDefault();
            alert("Speech recognition is not supported in this browser.");
        };
        return;
    }

    let isRecording = false;

    recognition.onstart = () => {
        isRecording = true;
        micBtn.style.color = '#F43F5E';
        micBtn.style.animation = 'pulse 1.5s infinite';
    };

    recognition.onresult = (event) => {
        let transcript = '';
        for (let i = event.resultIndex; i < event.results.length; ++i) {
            transcript += event.results[i][0].transcript;
        }
        setReactInputValue(chatInput, transcript);
    };

    recognition.onerror = (event) => {
        console.error("Speech recognition error", event.error);
        isRecording = false;
        micBtn.style.color = '#888';
        micBtn.style.animation = 'none';
    };

    recognition.onend = () => {
        isRecording = false;
        micBtn.style.color = '#888';
        micBtn.style.animation = 'none';
    };

    micBtn.onclick = (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (isRecording) {
            recognition.stop();
        } else {
            setReactInputValue(chatInput, '');
            recognition.start();
        }
    };
}

// Add CSS animation for pulsing mic
const style = document.createElement('style');
style.innerHTML = `
@keyframes pulse {
    0% { transform: scale(1); }
    50% { transform: scale(1.1); }
    100% { transform: scale(1); }
}`;
document.head.appendChild(style);

// --------------------------------------------------------
// 3. Main Observer Loop
// --------------------------------------------------------
const observer = new MutationObserver((mutations) => {
    // A. Guest Login Button Injection
    const loginForm = document.querySelector('form');
    const emailInput = document.querySelector('input[name="email"], input[type="email"]');
    const passInput = document.querySelector('input[name="password"], input[type="password"]');
    const submitBtn = document.querySelector('button[type="submit"]');

    if (loginForm && emailInput && passInput && submitBtn) {
        if (!document.getElementById('guest-login-btn')) {
            const guestBtn = document.createElement('button');
            guestBtn.id = 'guest-login-btn';
            guestBtn.innerText = 'Login as Guest';
            guestBtn.type = 'button';
            guestBtn.style.cssText = 'width: 100%; margin-top: 15px; padding: 10px; background-color: #F43F5E; color: white; border: none; border-radius: 8px; cursor: pointer; font-size: 16px; font-weight: 500; font-family: inherit; transition: opacity 0.2s;';
            guestBtn.onmouseover = () => guestBtn.style.opacity = '0.9';
            guestBtn.onmouseout = () => guestBtn.style.opacity = '1';
            
            guestBtn.onclick = (e) => {
                e.preventDefault();
                setReactInputValue(emailInput, 'guest');
                setReactInputValue(passInput, 'guest');
                sessionStorage.setItem('isGuestUser', 'true');
                setTimeout(() => submitBtn.click(), 100);
            };
            submitBtn.parentNode.appendChild(guestBtn);
        }
    }

    // B. Intercept File Upload Button
    if (sessionStorage.getItem('isGuestUser') === 'true') {
        // Disable actual file inputs to prevent system dialog
        document.querySelectorAll('input[type="file"]').forEach(fi => {
            if (!fi.disabled) fi.disabled = true;
        });

        // Bind popup to the upload button
        const uploadBtn = document.getElementById('upload-button') || document.querySelector('button[aria-label*="attach" i], button[aria-label*="upload" i]');
        if (uploadBtn && !uploadBtn.dataset.guestPatched) {
            uploadBtn.dataset.guestPatched = "true";
            uploadBtn.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                showGuestModal();
            }, {capture: true});
        }
    }

    // C. Inject Microphone Button
    injectMicButton();
});

observer.observe(document.body, { childList: true, subtree: true });
