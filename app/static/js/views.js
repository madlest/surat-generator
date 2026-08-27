// Pergantian antar tampilan (dashboard / form / wizard admin).
// Tidak ada reload halaman: cukup toggle class .active.

export function showView(viewId) {
  document
    .querySelectorAll(".view")
    .forEach((v) => v.classList.remove("active"));
  document.getElementById(viewId).classList.add("active");
  window.scrollTo({
    top: 0,
    behavior: "instant" in window ? "instant" : "auto",
  });
}
