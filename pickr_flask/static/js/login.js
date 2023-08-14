const closeAlert = document.querySelector(".alert button");
if (closeAlert){
  closeAlert.addEventListener("click", (e) => {
    e.preventDefault();
    closeAlert.parentNode.style.display = "none";
  }, false)
}
