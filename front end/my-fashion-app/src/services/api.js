const API_BASE_URL = 'http://localhost:8000';

/**
 * Generate appearance by sending user image and requirements to backend
 * @param {File} imageFile - The uploaded image file
 * @param {string} requirements - User requirements text
 * @param {string} style - Selected style preference (e.g., 'Streetwear', 'Minimalist')
 * @param {string} userPrompt - Additional special request from user
 * @returns {Promise<Object>} API response with agent_summary, diagram, and final_image
 */
export async function generatePlan(requirements, style, userPrompt, budget, location, gender, age) {
  const formData = new FormData();
  formData.append('requirements', requirements || 'General outfit assistance');
  if (style) formData.append('style', style);
  if (userPrompt) formData.append('user_prompt', userPrompt);
  formData.append('budget', budget);
  formData.append('location', location);
  
  formData.append('gender', gender);
  formData.append('age', age);

  const response = await fetch(`${API_BASE_URL}/api/generate-plan`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) throw new Error('Plan generation failed');
  return response.json();
}
export async function generateVisuals(imageFile, internalContext) {
  const formData = new FormData();
  formData.append('image', imageFile);
  // 將 Context 物件轉字串傳回後端
  formData.append('internal_context', JSON.stringify(internalContext));

  const response = await fetch(`${API_BASE_URL}/api/generate-visuals`, {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) throw new Error('Visuals generation failed');
  return response.json();
}
/**
 * Health check for the backend API
 * @returns {Promise<Object>} Health status
 */
export async function checkHealth() {
  const response = await fetch(`${API_BASE_URL}/health`);
  return response.json();
}
