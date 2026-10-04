(() => {
    function isMobile() {
        const isMobileUA = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(
            navigator.userAgent
        );
        const isSmallScreen = window.matchMedia("(max-width: 768px)").matches;
        return isMobileUA || isSmallScreen;
    }

    function getBrowserType() {
        return window.navigator.userAgent.indexOf("Edg") > -1 ? 'edge' : 'chrome';
    }

    function getStoreURL(browserType = 'chrome') {
        const url = {
            edge: {
                webStore: 'https://microsoftedge.microsoft.com/addons/detail/dbepbhhcmhodojepbagfppgpieeplpik',
                reviewURL: 'https://microsoftedge.microsoft.com/addons/detail/dbepbhhcmhodojepbagfppgpieeplpik'
            },
            chrome: {
                webStore: 'https://chromewebstore.google.com/detail/nfmmmhanepmpifddlkkmihkalkoekpfd',
                reviewURL: 'https://chromewebstore.google.com/detail/nfmmmhanepmpifddlkkmihkalkoekpfd/reviews'
            }
        }
        return url[browserType];
    }

    function installBtnShow() {
        const browserType = getBrowserType();
        const btnID = `${browserType}Install`;
        document.getElementById(btnID)?.classList.remove('d-none');
        setTimeout(() => {
            const $UILoading = document.getElementById('UILoading');
            const $UIInstall = document.getElementById('UIInstall');
            const version = document.body.dataset.version || null;
            if ($UILoading && !version) {
                $UILoading.classList.add('d-none');
                $UIInstall.classList.remove('d-none');
            }
        }, 3000);
    }

    function faqCollapseInit() {
        document.querySelectorAll('.faq-collapse').forEach($collapse => {
            const $header = $collapse.querySelector('.faq-header');

            const $dash = $header.querySelector('.collapse-dash');
            const $plus = $header.querySelector('.collapse-plus');

            const $body = $collapse.querySelector('.faq-body');
            const collapse = new bootstrap.Collapse($body, {
                toggle: false,
            });
            $body.addEventListener('hidden.bs.collapse', event => {
                $dash.classList.add('d-none');
                $plus.classList.remove('d-none');
            });
            $body.addEventListener('shown.bs.collapse', event => {
                $dash.classList.remove('d-none');
                $plus.classList.add('d-none');
            });
            $header.onclick = () => collapse.toggle();
        });
    }

    function reviewModalInit() {
        const $modal = document.getElementById('review');
        const $reviewBtn = document.getElementById('reviewBtn');
        const modal = new bootstrap.Modal($modal);
        $modal.addEventListener('hidden.bs.modal', () => {
            if (!localStorage.getItem('reviewed')) localStorage.setItem('reviewed', 1);
        });
        $reviewBtn.onclick = () => {
            const browserType = getBrowserType();
            const {reviewURL} = getStoreURL(browserType);
            window.open(reviewURL);
            modal.hide();
        };
        document.addEventListener('reviewToast', function(event) {
            if (isMobile()) return;
            let size = event.detail?.size;
            if (localStorage.getItem('reviewed')) return;
            if (!size) return;
            size = parseInt(size);
            if (size > 100*1024*1024 && size < 4*1024*1024*1024) {
                setTimeout(() => {modal.show();}, 5000);
            }
        });
    }


    function customAds() {
        const lang = navigator.language.toLowerCase();
        const isSimplifiedChinese = lang === 'zh-cn' || lang.startsWith('zh-cn-');
        const userAgent = navigator.userAgent;
        const isWindows = userAgent.includes('Win32') || userAgent.includes('Windows');
        if (!isSimplifiedChinese || !isWindows) return;
        const style = document.createElement('style');
        style.textContent = `.gads #backupad{display: none}.gads:has(ins.adsbygoogle[data-ad-status="unfilled"]) #backupad{display: block !important;}`;
        document.head.appendChild(style);
        const backupad = document.querySelector('#backupad');
        if (backupad) {
            backupad.innerHTML = `<div class="px-5 py-3 border text-start position-relative bg-white">
            <div class="d-flex justify-content-between align-items-center">
                <div>
                    <span class="fs-3 fw-bold">\u0045\u0046\u0065\u0074\u0063\u0068\u0020\u89c6\u9891\u4e0b\u8f7d\u5668</span>
                    <p class="lead">\u2014\u2014\u0020\u0046\u0065\u0074\u0063\u0068\u0056\u684c\u9762\u7248\u672c\uff0c\u66f4\u7a33\u5065\u7684\u4e0b\u8f7d\u65b9\u5f0f\uff0c\u66f4\u597d\u5730\u7ba1\u7406\u4e0b\u8f7d\u6587\u4ef6\u3002</p>
                </div>
                <div>
                    <a class="btn btn-lg btn-primary stretched-link px-5 py-3" href="https://efetch.net/cn" target="_blank">\u7acb\u5373\u4f53\u9a8c</a>
                </div>
            </div>
            <span class="text-black-50 position-absolute top-0 end-0 small me-1 mt-1">Advertise</span>
        </div>`;
        }
    }

    function pageInit() {
        faqCollapseInit();
        installBtnShow();
        reviewModalInit();
        customAds();
    }


    pageInit();

})()