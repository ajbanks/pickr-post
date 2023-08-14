const sidebar = document.querySelector(".sidebar");
const navOpts = document.querySelector("#nav-options");
const mainContainer = document.querySelector(".content");

// nav sidebar collapse/expand
document.querySelector('#exit').onclick = toggleSidebar;
document.querySelector("#menu").onclick = toggleSidebar;

function toggleSidebar() {
  sidebar.classList.toggle('sidebar_small');
  mainContainer.classList.toggle('content_large');
  navOpts.classList.toggle('hide');
}


// alert close
const closeAlert = document.querySelector(".message-modal button");
if (closeAlert){
  closeAlert.addEventListener("click", (e) => {
    e.preventDefault();
    closeAlert.parentNode.style.display = "none";
  }, false)
}


///
/// Stripe Checkout
let stripeAPI;
const upgradeBtn = document.querySelector("#upgradebtn")

fetch("/stripe-pub-key")
  .then((resp) => { return resp.json(); })
  .then((data) => {
    stripeAPI = Stripe(data.publicKey);
    upgradeBtn.addEventListener("click", () => {
      fetch("/checkout-session")
        .then((resp) => { return resp.json(); })
        .then((data) => {
          console.log(data.sessionId);
          return stripeAPI.redirectToCheckout({sessionId: data.sessionId});
        })
        .then((res) =>  { console.log(res); })
    })
  });
