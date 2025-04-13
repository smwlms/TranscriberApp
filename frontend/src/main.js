import './index.css'         // Import the global CSS file we just created
import App from './App.svelte' // Import the root Svelte component

// Create a new instance of the main App component
const app = new App({
  // Tell Svelte to render the component inside the HTML element with the ID 'app'
  target: document.getElementById('app'),
})

// Export the app instance (common practice, useful for integrations/testing)
export default app