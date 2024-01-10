function initThebelab() {
  let activateButton = document.getElementById("thebelab-activate-button");
  if (activateButton.classList.contains("thebelab-active")) {
    return;
  }

  // Place all outputs below the source where this was not the case
  // to make them recognizable by thebelab
  let codeBelows = document.getElementsByClassName("thebelab-below");
  for (var i = 0; i < codeBelows.length; i++) {
    let prev = codeBelows[i];
    // Find previous sibling element, compatible with IE8
    do prev = prev.previousSibling;
    while (prev && prev.nodeType !== 1);
    swapSibling(prev, codeBelows[i]);
  }

  thebelab.bootstrap();
  activateButton.classList.add("thebelab-active");
}

function swapSibling(node1, node2) {
  node1.parentNode.replaceChild(node1, node2);
  node1.parentNode.insertBefore(node2, node1);
}
