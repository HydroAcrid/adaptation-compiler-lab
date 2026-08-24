import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import "@fontsource-variable/instrument-sans";
import "@fontsource-variable/newsreader";

import App from "./App";
import "./styles.css";

const root = document.getElementById("root");
if (!root) throw new Error("Temper root element is unavailable");

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
