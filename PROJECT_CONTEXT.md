# Project Overview: Aura Stylist (AI Fashion & Virtual Try-On App)

## 1. Project Background
This is a Final Year Project (FYP) focused on creating a personalized AI digital stylist Android application. The app transitions from a simple AI image generator to a practical tool based on the user's real wardrobe.
The goal is to allow users to upload photos of their clothes, use an AI Agent to recommend outfits based on aesthetics/weather/events, and generate realistic virtual try-on images.

## 2. System Architecture
- **Frontend (Mobile App):** React Native with Expo (Migrating from React/Vite web).
- **Backend (API Server):** Python FastAPI.
- **AI Agent (Brain):** LangGraph (with LLMs like Gemini/Claude) for aesthetic reasoning, styling combinations, and user preference memory.
- **Image Generation (Virtual Try-On):** IDM-VTON (Diffusion Model) deployed on cloud GPU to generate realistic try-on images based on the user's base image and selected garment.

## 3. Core Workflows
1. **Wardrobe Digitization:** User uploads a photo of a garment. App sends it to FastAPI, removes background, categorizes it, and saves to the Database.
2. **Outfit Recommendation:** User inputs a scenario (e.g., "Interview tomorrow"). LangGraph agent queries the wardrobe DB, matches items, and outputs a styling plan.
3. **Virtual Try-On Generation:** Frontend sends the user's full-body base image + selected garment image to the backend. Backend triggers IDM-VTON, waits for the result, and returns the generated image to the Android app.

## 4. Current Development Status
- The old frontend was built in React (Web) using Tailwind CSS.
- **CURRENT PHASE:** We are currently migrating the frontend to an Android App using Expo (React Native). 
- A basic MVP UI (`App.js`) has been set up with `expo-image-picker` to capture photos.
- The backend FastAPI structure and LangGraph logic exist but need to be properly connected to the new React Native frontend.

## 5. Next Steps & Tasks for Claude
1. **API Integration:** Connect the React Native frontend to the local FastAPI server. Implement `FormData` image uploads from Android to Python.
2. **Database Setup:** Design and implement a database (e.g., SQLite or Supabase) to store user wardrobe items (thumbnails locally, full images on cloud/backend).
3. **Async Task Handling:** IDM-VTON generation takes 10-30 seconds. Help implement a robust loading state or async polling mechanism between React Native and FastAPI to handle long-running generation tasks without blocking the UI.
4. **UI/UX Refinement:** Convert the remaining complex UI components (like the chat interface and the Tinder-like swipe aesthetic tuner) from HTML/Tailwind to React Native `StyleSheet` and generic components.

## 6. Coding Conventions & Rules
- **Frontend:** Use functional components, React Hooks (`useState`, `useEffect`), and `StyleSheet.create` for styling. Avoid HTML tags (`<div>`, `<img>`); strictly use React Native components (`<View>`, `<Image>`, `<Text>`).
- **Backend:** Use async/await in FastAPI routes. Ensure strict typing with Pydantic models.
- **Network:** When testing on physical Android devices via Expo, always use the machine's local IP address (e.g., `http://192.168.X.X:8000`) instead of `localhost`.