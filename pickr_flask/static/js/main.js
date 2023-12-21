////
// nav sidebar collapse/expand
const sidebar = document.querySelector(".sidebar");
const navOpts = document.querySelector("#nav-options");
const mainContainer = document.querySelector(".content");
document.querySelector('#exit').onclick = toggleSidebar;
document.querySelector("#menu").onclick = toggleSidebar;

function toggleSidebar() {
  sidebar.classList.toggle('sidebar_small');
  mainContainer.classList.toggle('content_large');
  navOpts.classList.toggle('hide');
}

////
// accordion collapse/expand
const accordions = document.getElementsByClassName("accordion");

function toggleAccordion(a) {
  a.classList.toggle("active");
  let content = a.nextElementSibling;
  if (content.style.maxHeight) {
    content.style.maxHeight = null;
  } else {
    content.style.maxHeight = content.scrollHeight + "px";
  }
}

for (let i = 0; i < accordions.length; i++) {
  accordions[i].addEventListener("click", (e) => {
    toggleAccordion(accordions[i]);
  })
}

// toggle the first one
// if (accordions.length > 0) {
//   toggleAccordion(accordions[0])
// }


////
// alert close
const closeAlert = document.querySelector(".message-modal button");
if (closeAlert){
  closeAlert.addEventListener("click", (e) => {
    e.preventDefault();
    closeAlert.parentNode.style.display = "none";
  }, false)
}


////
// HTMX event hooks

// add timezone info to htmx requests
document.body.addEventListener("htmx:configRequest", function(e) {
  let classlist = e.srcElement.classList;
  if (classlist.contains("schedule-button") ||
      classlist.contains("back-button") ||
      classlist.contains("submit-button")) {
    let dtInfo = Intl.DateTimeFormat().resolvedOptions();
    e.detail.parameters["timezone"] = encodeURIComponent(dtInfo.timeZone);
    e.detail.parameters["locale"] = encodeURIComponent(dtInfo.locale);
  }
})


// TODO(meiji163): remove this terrible hack
// it makes the accordian not overflow when HTMX request
// increases card elements height
document.body.addEventListener("htmx:afterSwap", function(e) {
  if (e.srcElement.classList.contains("card")) {
    for (let i = 0; i < accordions.length; i++) {
      let content = accordions[i].nextElementSibling;
      if (content.contains(e.srcElement)) {
        content.style.maxHeight = content.scrollHeight + "px";
        break;
      }
    }
  }
})


////
// Stripe Checkout
let stripeAPI;
const upgradeBtn = document.querySelector("#upgradebtn")

if (upgradeBtn != null){
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
}
