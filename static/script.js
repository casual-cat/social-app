// static/script.js

function openStoryModal(mediaUrl, username) {
  const modal = document.getElementById("storyModal");
  const closeModal = document.getElementById("closeModal");
  const modalMedia = document.getElementById("modalMedia");
  const modalUser = document.getElementById("modalUser");

  // Clear old
  modalMedia.innerHTML = "";

  const lowerUrl = mediaUrl.toLowerCase();
  if (lowerUrl.endsWith(".png") || lowerUrl.endsWith(".jpg") ||
      lowerUrl.endsWith(".jpeg") || lowerUrl.endsWith(".gif")) {
    const img = document.createElement("img");
    img.src = mediaUrl;
    modalMedia.appendChild(img);
  } else if (lowerUrl.endsWith(".mp4") || lowerUrl.endsWith(".mov") ||
             lowerUrl.endsWith(".avi")) {
    const vid = document.createElement("video");
    vid.src = mediaUrl;
    vid.controls = true;
    modalMedia.appendChild(vid);
  } else {
    const p = document.createElement("p");
    p.textContent = "Unsupported format.";
    modalMedia.appendChild(p);
  }

  modalUser.textContent = `Story by: ${username}`;
  modal.style.display = "block";

  // Hook up close
  const xClose = document.getElementById("closeModal") || document.querySelector(".close");
  if (xClose) {
    xClose.onclick = () => {
      modal.style.display = "none";
    };
  }

  // Close if click outside
  window.onclick = (event) => {
    if (event.target === modal) {
      modal.style.display = "none";
    }
  };
}
