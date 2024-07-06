/**
 * Configure the Unpoly framework (https://unpoly.com).
 * If this file starts to acrete a lot of code, it's probably time to move
 * to a big-kid frontend implementation, like <shudder> NextJS...
 **/

// Link Unpoly's nav feedback with Bulma's nav styles
// https://unpoly.com/up.feedback
// https://unpoly.com/up.feedback.config#config.currentClasses
up.feedback.config.currentClasses.push("is-tab");
up.feedback.config.currentClasses.push("is-active");

// Clear flashes after 5 seconds
// https://unpoly.com/flashes#clearing-flashes
up.compiler('[up-flashes] > *', function(message) {
  setTimeout(() => up.destroy(message), 5000)
});

// Enable code highlighting for all <code> elements
// https://unpoly.com/up.compiler
// https://highlightjs.org/
up.compiler('code', function(element) {
  hljs.highlightAll();
});
