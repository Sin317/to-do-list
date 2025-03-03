// utils.js

/**
 * Formats a date object into a human-readable time string.
 *
 * @param {Date} date - The date object to format.
 * @returns {string} - The formatted time string.
 */
function formatTime(date) {
    if (!(date instanceof Date)) {
      console.error("Invalid date object provided to formatTime.");
      return "";
    }
    return date.toLocaleTimeString();
  }
  
  /**
   * Creates a new list item element (<li>) with the given text.
   *
   * @param {string} text - The text content for the list item.
   * @returns {HTMLLIElement} - The created list item element.
   */
  function createListItem(text) {
    if (typeof text !== "string") {
      console.error("Invalid text provided to createListItem.");
      return document.createElement("li"); // Return empty li to prevent errors.
    }
    const listItem = document.createElement("li");
    listItem.textContent = text;
    return listItem;
  }
  
  /**
   * Clears all child elements from a given DOM element.
   *
   * @param {HTMLElement} element - The DOM element to clear.
   */
  function clearElementChildren(element) {
    if (!(element instanceof HTMLElement)) {
      console.error("Invalid HTMLElement provided to clearElementChildren.");
      return;
    }
    while (element.firstChild) {
      element.removeChild(element.firstChild);
    }
  }
  
  /**
   * Logs an error message to the console with a consistent prefix.
   *
   * @param {string} message - The error message to log.
   */
  function logError(message) {
    console.error("[To-Do App Error]:", message);
  }