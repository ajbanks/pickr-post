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
if (accordions.length > 0) {
  toggleAccordion(accordions[0])
}


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
// twitter share button
const tweetCards = document.getElementsByClassName("card tweet");
const twitterBtns = document.getElementsByClassName("twitter-button");
const twitterURL = "https://twitter.com/intent/tweet/"
const windowOpts = "menubar=no,status=no,height=400,width=500";

function openTweetWindow(text){
  let query = `text=${text}`;
  let linkTarget = "_top"; // "_blank" opens a new window
  return window.open(`${twitterURL}?${query}&`, linkTarget, windowOpts)
               .focus();
}

// get the tweet text and open twitter intent with it
function listenOnTwitterBtns(){
  for (let i = 0; i < tweetCards.length; i++) {
    let suggestedPost = tweetCards[i].getElementsByClassName("suggested-post")[0];
    let text = suggestedPost.firstElementChild.innerHTML;
    let tweetBtn = tweetCards[i].getElementsByClassName("twitter-button")[0];
    tweetBtn.addEventListener("click", (e) => {
      console.log(text);
      openTweetWindow(text);
    })
  }
}


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
