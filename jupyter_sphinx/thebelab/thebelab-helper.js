function initThebelab() {
    let activateButton = document.getElementById("thebelab-activate-button");
    if (activateButton.classList.contains('thebelab-active')) {
        return;
    }
    thebelab.bootstrap();
    activateButton.classList.add('thebelab-active')
}
