import React, { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { generatePlan, generateVisuals } from './services/api';
import { Loader2 } from 'lucide-react';
import {
  Upload,
  Sparkles,
  Zap,
  Share2,
  RefreshCcw,
  Shirt,
  Palette,
  Maximize2,
  CheckCircle2,
  ScanLine,
  MessageSquare,
  Send,
  User,
  Bot,
  AlertCircle,
  MapPin,
  DollarSign,
  ExternalLink,
  X // Close icon for lightbox
} from 'lucide-react';
// --- Helper: Image Loader Component ---
const ImageLoader = () => (
  <div className="w-full h-full flex flex-col items-center justify-center bg-white/5 animate-pulse text-gray-400">
    <Loader2 className="w-10 h-10 animate-spin mb-2 text-purple-400" />
    <span className="text-xs font-mono">AI Visualizing...</span>
  </div>
);

// --- API Service Integration ---
const generateAppearance = async (imageFile, requirements, style, userPrompt, budget, location) => {
  const formData = new FormData();
  formData.append('image', imageFile);
  formData.append('requirements', requirements);
  formData.append('style', style);
  formData.append('user_prompt', userPrompt || '');
  formData.append('budget', budget);
  formData.append('location', location);

  // 注意：確保後端運行於 localhost:8000
  const API_URL = 'http://localhost:8000/api/generate-appearance';

  try {
    const response = await fetch(API_URL, {
      method: 'POST',
      body: formData,
    });

    if (!response.ok) {
      const errorText = await response.text();
      throw new Error(`Server error: ${response.status} - ${errorText}`);
    }

    return await response.json();
  } catch (error) {
    console.error("API Call failed:", error);
    throw error;
  }
};

// --- Helper: Simple Markdown Renderer ---
const SimpleMarkdown = ({ text }) => {
  if (!text) return null;
  let processedText = text.replace(/([^\n])(\s*-\s)/g, '$1\n$2');

  return (
    <div className="space-y-3 text-gray-300 text-sm leading-relaxed font-sans">
      {processedText.split('\n').map((line, i) => {
        if (line.trim().startsWith('###')) {
          return <h3 key={i} className="text-purple-300 font-bold text-lg mt-4 mb-2">{line.replace(/#/g, '').trim()}</h3>;
        }
        const parts = line.split(/(\*\*.*?\*\*|\[.*?\]\(.*?\))/g);
        return (
          <p key={i} className="min-h-[1em]">
            {parts.map((part, j) => {
              if (part.startsWith('**') && part.endsWith('**')) {
                return <strong key={j} className="text-white font-semibold">{part.replace(/\*\*/g, '')}</strong>;
              }
              const linkMatch = part.match(/\[(.*?)\]\((.*?)\)/);
              if (linkMatch) {
                return (
                  <a key={j} href={linkMatch[2]} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-cyan-400 hover:text-cyan-300 underline underline-offset-2 mx-1 font-medium transition-colors">
                    {linkMatch[1]} <ExternalLink size={10} />
                  </a>
                );
              }
              return part;
            })}
          </p>
        );
      })}
    </div>
  );
};

// --- Components ---

// GlassCard: Updated to accept onClick (for zoom trigger)
const GlassCard = ({ children, className = "", delay = 0, onClick }) => (
  <motion.div 
    initial={{ opacity: 0, y: 20 }}
    animate={{ opacity: 1, y: 0 }}
    transition={{ duration: 0.5, delay, ease: "easeOut" }}
    onClick={onClick}
    className={`relative overflow-hidden rounded-3xl border border-white/10 bg-white/5 backdrop-blur-xl shadow-2xl ${className} ${onClick ? 'cursor-pointer' : ''}`}
  >
    <div className="absolute inset-0 bg-gradient-to-br from-white/5 to-transparent pointer-events-none" />
    <div className="relative z-10 h-full">{children}</div>
  </motion.div>
);

const Pill = ({ label, active, onClick }) => (
  <button
    onClick={onClick}
    className={`px-4 py-2 rounded-full text-xs font-medium transition-all duration-300 border ${
      active 
        ? "bg-purple-500/20 border-purple-400 text-purple-200 shadow-[0_0_15px_rgba(168,85,247,0.3)]" 
        : "bg-white/5 border-white/10 text-gray-400 hover:bg-white/10 hover:border-white/20"
    }`}
  >
    {label}
  </button>
);

const LoadingStep = ({ label, isActive, isCompleted }) => (
  <div className={`flex items-center gap-3 ${isActive ? 'opacity-100 scale-105' : 'opacity-50'} transition-all duration-500`}>
    <div className={`w-6 h-6 rounded-full flex items-center justify-center border ${
      isCompleted ? 'bg-green-500 border-green-500 text-black' : 
      isActive ? 'bg-purple-500 border-purple-500 animate-pulse text-white' : 'border-white/20'
    }`}>
      {isCompleted ? <CheckCircle2 size={14} /> : <div className="w-2 h-2 rounded-full bg-current" />}
    </div>
    <span className={`text-sm ${isActive ? 'text-purple-300 font-bold' : 'text-gray-400'}`}>{label}</span>
  </div>
);

const ChatMessage = ({ role, text }) => (
  <motion.div 
    initial={{ opacity: 0, x: role === 'ai' ? -10 : 10 }}
    animate={{ opacity: 1, x: 0 }}
    className={`flex gap-3 mb-4 ${role === 'user' ? 'flex-row-reverse' : ''}`}
  >
    <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${
      role === 'ai' ? 'bg-purple-500/20 text-purple-300' : 'bg-white/10 text-white'
    }`}>
      {role === 'ai' ? <Bot size={16} /> : <User size={16} />}
    </div>
    <div className={`p-3 rounded-2xl text-sm max-w-[80%] ${
      role === 'ai' 
        ? 'bg-purple-500/10 border border-purple-500/20 text-gray-200 rounded-tl-none' 
        : 'bg-white/10 border border-white/10 text-white rounded-tr-none'
    }`}>
      <SimpleMarkdown text={text} />
    </div>
  </motion.div>
);

const ImageLightbox = ({ src, alt, onClose }) => (
  <motion.div
    initial={{ opacity: 0 }}
    animate={{ opacity: 1 }}
    exit={{ opacity: 0 }}
    className="fixed inset-0 z-50 flex items-center justify-center bg-black/90 backdrop-blur-sm p-4"
    onClick={onClose}
  >
    <div className="relative max-w-5xl max-h-screen w-full h-full flex items-center justify-center">
      <button 
        onClick={onClose}
        className="absolute top-4 right-4 p-2 bg-white/10 hover:bg-white/20 rounded-full text-white transition-colors z-50"
      >
        <X size={24} />
      </button>
      <motion.img
        initial={{ scale: 0.9 }}
        animate={{ scale: 1 }}
        src={src}
        alt={alt}
        className="max-w-full max-h-full object-contain rounded-lg shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      />
    </div>
  </motion.div>
);

export default function FashionAIApp() {
  const [appState, setAppState] = useState('input');
  const [loadingStep, setLoadingStep] = useState(0);
  const [age, setAge] = useState('Young Adult (20-35)');
  const [gender, setGender] = useState('Men');
  const [selectedStyle, setSelectedStyle] = useState('Streetwear');
  const [uploadedImage, setUploadedImage] = useState(null);
  const [imageFile, setImageFile] = useState(null);
  const [userRequest, setUserRequest] = useState('');
  const [budget, setBudget] = useState(500);
  const [location, setLocation] = useState('Hong Kong');
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef(null);
  const [visualsLoading, setVisualsLoading] = useState(false);
  const [apiResult, setApiResult] = useState(null);
  const [errorMessage, setErrorMessage] = useState('');
  const [chatInput, setChatInput] = useState('');
  const [chatHistory, setChatHistory] = useState([]);
  const chatEndRef = useRef(null);

  // --- Zoom State (Restored) ---
  const [zoomImage, setZoomImage] = useState(null);

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatHistory, appState]);

  useEffect(() => {
    let interval;
    if (appState === 'loading') {
      setLoadingStep(0);
      interval = setInterval(() => {
        setLoadingStep(prev => (prev < 3 ? prev + 1 : prev));
      }, 3000);
    }
    return () => clearInterval(interval);
  }, [appState]);

  const handleFile = (file) => {
    if (file) {
      setUploadedImage(URL.createObjectURL(file));
      setImageFile(file);
    }
  };

  const handleReset = () => {
    setAppState('input');
    setUploadedImage(null);
    setImageFile(null);
    setApiResult(null);
    setUserRequest('');
    setChatHistory([]);
    setVisualsLoading(false);
  };

  // 3. Handle Chat Message
  const handleSendMessage = (e) => {
    e.preventDefault();
    if (!chatInput.trim()) return;
    
    // Add user message immediately
    const userMsg = chatInput;
    setChatHistory(prev => [...prev, { role: 'user', text: userMsg }]);
    setChatInput('');

    // Mock AI response for now (since backend chat API isn't connected yet)
    setTimeout(() => {
      setChatHistory(prev => [...prev, { 
        role: 'ai', 
        text: `I can help you with styling advice for this ${selectedStyle} look! What specific details would you like to know?` 
      }]);
    }, 1000);
  };

  const handleGenerate = async () => {
    if (!imageFile) return;
    
    // Step 1: UI 進入 Loading
    setAppState('loading');
    setErrorMessage('');
    setLoadingStep(0);
    setApiResult(null); // Clear previous result
    const fullRequest = userRequest || 'General outfit advice';
    try {
      // Step 2: 呼叫快速的 Plan API
      const planResult = await generatePlan(
        fullRequest,
        selectedStyle,
        userRequest, // using same field for userPrompt
        budget,
        location,
        gender,
        age
      );

      // Step 3: 拿到文字結果，立刻顯示 UI
      setApiResult(planResult); // 這時候 diagram 和 final_image 是空的
      setChatHistory([{ role: 'ai', text: "✨ 文字分析已完成！正在為您生成虛擬試穿效果..." }]);
      setAppState('result'); // 切換畫面到結果頁
      
      // Step 4: 啟動圖片生成 (異步)
      setVisualsLoading(true);
      
      try {
        const visualsResult = await generateVisuals(
          imageFile,
          planResult.internal_context
        );

        // Step 5: 圖片好了，更新 State
        setApiResult(prev => ({
            ...prev,
            diagram: visualsResult.diagram,
            final_image: visualsResult.final_image
        }));
      } catch (imgError) {
        console.error("Visual gen failed", imgError);
        // 可以選擇顯示錯誤或保留 loading 狀態
      } finally {
        setVisualsLoading(false);
      }

    } catch (error) {
      console.error(error);
      setErrorMessage(error.message || 'Failed to generate outfit.');
      setAppState('error');
    }
  };

  return (
    <div className="min-h-screen w-full bg-[#0a0a0f] text-white font-sans selection:bg-purple-500/30 overflow-x-hidden">
      
      {/* Lightbox Overlay (Restored) */}
      <AnimatePresence>
        {zoomImage && (
          <ImageLightbox 
            src={zoomImage.src} 
            alt={zoomImage.alt} 
            onClose={() => setZoomImage(null)} 
          />
        )}
      </AnimatePresence>

      {/* Background Ambience */}
      <div className="fixed inset-0 pointer-events-none">
        <div className="absolute top-[-10%] left-[-10%] w-[50vw] h-[50vw] bg-purple-900/20 rounded-full blur-[120px]" />
        <div className="absolute bottom-[-10%] right-[-10%] w-[50vw] h-[50vw] bg-blue-900/10 rounded-full blur-[120px]" />
        <div className="absolute inset-0 bg-[url('https://grainy-gradients.vercel.app/noise.svg')] opacity-20" />
      </div>

      <main className="relative z-10 max-w-7xl mx-auto px-4 py-8 lg:py-12 flex flex-col min-h-screen">
        <header className="flex justify-between items-center mb-8">
          <div className="flex items-center gap-2">
            <div className="w-10 h-10 bg-gradient-to-tr from-purple-500 to-cyan-500 rounded-xl flex items-center justify-center shadow-lg shadow-purple-500/20">
              <Sparkles className="text-white w-6 h-6" />
            </div>
            <div>
              <h1 className="text-xl font-bold tracking-tight text-transparent bg-clip-text bg-gradient-to-r from-white to-gray-400">
                AURA <span className="font-light">STYLIST</span>
              </h1>
            </div>
          </div>
        </header>

        <AnimatePresence mode="wait">
          {appState === 'input' && (
            <motion.div 
              key="input"
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, filter: "blur(10px)", scale: 1.05 }}
              className="w-full max-w-6xl mx-auto"
            >
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
                
                {/* Left: Upload */}
                <div className="lg:col-span-5 h-[500px] lg:h-[650px]">
                  <GlassCard className="h-full flex flex-col p-1 cursor-pointer transition-all hover:border-purple-500/30">
                    <div 
                      className={`
                        flex-1 border-2 border-dashed rounded-[20px] transition-all duration-300 relative overflow-hidden
                        flex flex-col items-center justify-center
                        ${isDragging || uploadedImage ? 'border-purple-500/50 bg-purple-500/5' : 'border-white/10 hover:border-white/20 hover:bg-white/5'}
                      `}
                      onClick={() => fileInputRef.current?.click()}
                    >
                      <input type="file" ref={fileInputRef} className="hidden" accept="image/*" onChange={(e) => handleFile(e.target.files[0])} />
                      {uploadedImage ? (
                        <div className="relative w-full h-full">
                          <img src={uploadedImage} alt="Uploaded" className="w-full h-full object-cover" />
                          <div className="absolute top-4 right-4 p-2 bg-black/50 backdrop-blur-md rounded-full text-white/70 hover:text-white"
                             onClick={(e) => { e.stopPropagation(); setUploadedImage(null); }}>
                            <RefreshCcw className="w-4 h-4" />
                          </div>
                        </div>
                      ) : (
                        <div className="text-center p-8">
                          <div className="w-20 h-20 mx-auto bg-white/5 rounded-full flex items-center justify-center mb-6">
                            <Upload className="w-8 h-8 text-purple-300" />
                          </div>
                          <h3 className="text-xl font-medium text-white mb-2">Upload Photo</h3>
                          <p className="text-gray-500 text-xs">Tap to browse</p>
                        </div>
                      )}
                    </div>
                  </GlassCard>
                </div>

                {/* Right: Controls */}
                <div className="lg:col-span-7 flex flex-col gap-6">
                  <GlassCard className="flex-1 p-8 overflow-y-auto">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
                      <div>
                        <label className="flex items-center gap-2 text-sm font-semibold text-gray-300 mb-3">
                          <MapPin size={16} className="text-cyan-400" /> Location
                        </label>
                        <div className="flex flex-wrap gap-2">
                          {['Hong Kong', 'Tokyo', 'Seoul', 'London', 'New York'].map(loc => (
                            <Pill key={loc} label={loc} active={location === loc} onClick={() => setLocation(loc)} />
                          ))}
                        </div>
                      </div>
                      <div>
                         <label className="flex items-center gap-2 text-sm font-semibold text-gray-300 mb-3">
                          <DollarSign size={16} className="text-green-400" /> Budget (HKD): {budget}
                        </label>
                        <input 
                          type="range" 
                          min="100" 
                          max="5000" 
                          step="100" 
                          value={budget} 
                          onChange={(e) => setBudget(Number(e.target.value))}
                          className="w-full h-2 bg-white/10 rounded-lg appearance-none cursor-pointer accent-purple-500"
                        />
                        <div className="flex justify-between text-xs text-gray-500 mt-2">
                          <span>$100</span>
                          <span>$5000+</span>
                        </div>
                      </div>
                    </div>

                    <div className="mb-8">
                      <label className="flex items-center gap-2 text-sm font-semibold text-gray-300 mb-3">
                        <Palette size={16} className="text-purple-400" /> Style Aesthetic
                      </label>
                      <div className="flex flex-wrap gap-2">
                        {['Streetwear', 'Minimalist', 'Y2K', 'Luxury', 'Smart Casual', 'Vintage'].map(style => (
                          <Pill key={style} label={style} active={selectedStyle === style} onClick={() => setSelectedStyle(style)} />
                        ))}
                      </div>
                    </div>
                    <div className="mb-6">
                        <label className="flex items-center gap-2 text-sm font-semibold text-gray-300 mb-3">
                          <User size={16} className="text-pink-400" /> Gender Preference
                        </label>
                        <div className="flex flex-wrap gap-2">
                          {['Women', 'Men', 'Unisex'].map(g => (
                            <Pill 
                              key={g} 
                              label={g} 
                              active={gender === g} 
                              onClick={() => setGender(g)} 
                            />
                          ))}
                        </div>
                      </div>

                      <div className="mb-6">
                        <label className="flex items-center gap-2 text-sm font-semibold text-gray-300 mb-3">
                          <User size={16} className="text-orange-400" /> Age Group
                        </label>
                        <div className="flex flex-wrap gap-2">
                          {['Teenager (<20)', 'Young Adult (20-35)', 'Adult (36-50)', 'Mature (50+)'].map(a => (
                            <Pill 
                              key={a} 
                              label={a} 
                              active={age === a} 
                              onClick={() => setAge(a)} 
                            />
                          ))}
                        </div>
                      </div>
                    <div className="mb-4">
                       <label className="flex items-center gap-2 text-sm font-semibold text-gray-300 mb-3">
                        <MessageSquare size={16} className="text-yellow-400" /> Special Request
                      </label>
                       <textarea 
                         value={userRequest}
                         onChange={(e) => setUserRequest(e.target.value)}
                         placeholder="E.g., 'Going to a gallery opening, keep it monochromatic.'"
                         className="w-full h-24 bg-black/20 border border-white/10 rounded-xl p-4 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-purple-500/50 resize-none"
                       />
                    </div>
                  </GlassCard>

                  <button
                    onClick={handleGenerate}
                    disabled={!uploadedImage}
                    className={`
                      w-full py-4 rounded-2xl font-bold tracking-wide text-lg transition-all
                      ${uploadedImage 
                        ? 'bg-gradient-to-r from-purple-600 to-blue-600 hover:shadow-[0_0_30px_rgba(147,51,234,0.5)] text-white' 
                        : 'bg-white/5 text-gray-500 cursor-not-allowed'}
                    `}
                  >
                    GENERATE OUTFIT
                  </button>
                </div>
              </div>
            </motion.div>
          )}

          {appState === 'loading' && (
            <motion.div
              key="loading"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="w-full max-w-lg mx-auto mt-20"
            >
              <GlassCard className="p-8 text-center">
                <div className="relative w-32 h-32 mx-auto mb-8">
                  <div className="absolute inset-0 rounded-full border-4 border-purple-500/30 animate-spin border-t-purple-500" />
                  <div className="absolute inset-0 flex items-center justify-center">
                    <Sparkles className="w-10 h-10 text-white animate-pulse" />
                  </div>
                </div>
                <h3 className="text-2xl font-bold text-white mb-6">Curating Your Look</h3>
                <div className="space-y-4 text-left max-w-xs mx-auto">
                  <LoadingStep label="Analyzing Style Profile" isActive={loadingStep >= 0} isCompleted={loadingStep > 0} />
                  <LoadingStep label={`Searching Rakuten (${location} Weather)`} isActive={loadingStep >= 1} isCompleted={loadingStep > 1} />
                  <LoadingStep label="Checking Budget & Stock" isActive={loadingStep >= 2} isCompleted={loadingStep > 2} />
                  <LoadingStep label="Generating Visual Try-On" isActive={loadingStep >= 3} isCompleted={loadingStep > 3} />
                </div>
              </GlassCard>
            </motion.div>
          )}

          {appState === 'result' && (
            <motion.div key="result" initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="w-full">
              <div className="flex justify-between items-center mb-6">
                 <h2 className="text-2xl font-bold text-white">Your Curated Collection</h2>
                 <button onClick={handleReset} className="text-sm text-gray-400 hover:text-white underline">Start New Search</button>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
                
                {/* 圖片區域 (Restored Zoom Click) */}
                <div className="lg:col-span-4 flex flex-col gap-6">
                   {/* Diagram */}
                   <GlassCard 
                   className="aspect-[3/4] p-2 relative group bg-black/40 cursor-zoom-in"
                   onClick={() => setZoomImage({ 
                      src: apiResult?.diagram?.image_data || apiResult?.diagram?.image_url || uploadedImage, 
                      alt: "OOTD Diagram" 
                    })}
                   >
                    <div className="w-full h-full rounded-2xl overflow-hidden bg-[#1a1a20]">
                        {/* 邏輯判斷：如果正在Loading，顯示轉圈圈；否則顯示圖片 */}
                         {visualsLoading ? (
                     <ImageLoader />
                    ) : (
                   <img 
                     src={apiResult?.diagram?.image_data || apiResult?.diagram?.image_url || uploadedImage} 
                     className="w-full h-full object-contain" 
                     alt="OOTD Grid"
                   />
                      )}
                    </div>
                   </GlassCard>
                   
                   {/* Virtual Try On */}
                   <GlassCard 
                    className="aspect-[3/4] p-2 relative cursor-zoom-in group bg-black/40"
                    onClick={() => setZoomImage({ 
                      src: apiResult?.final_image?.image_data || apiResult?.final_image?.image_url || uploadedImage, 
                      alt: "Virtual Try-On" 
                    })}
                   >
                      <div className="w-full h-full rounded-2xl overflow-hidden relative">
                        {visualsLoading ? (
                    <ImageLoader />
                ) : (
                      <img 
                        src={apiResult?.final_image?.image_data || apiResult?.final_image?.image_url || uploadedImage} 
                        className="w-full h-full object-cover" 
                        alt="Try On"
                      />
                          )}
                        </div>
                  </GlassCard>
                </div>

                {/* 資訊與商品區域 */}
                <div className="lg:col-span-8 flex flex-col gap-6">
                  
                  {/* 文字分析 (Using SimpleMarkdown) */}
                  <GlassCard className="p-8">
                    <div className="flex items-center gap-3 mb-6 pb-4 border-b border-white/10">
                      <div className="w-10 h-10 rounded-full bg-purple-500/20 flex items-center justify-center">
                        <Bot className="text-purple-400" size={20} />
                      </div>
                      <div>
                        <h3 className="font-bold text-lg text-white">Stylist Recommendation</h3>
                        <p className="text-xs text-gray-500 uppercase tracking-wider">AI Analysis based on {location} weather</p>
                      </div>
                    </div>
                    {/* 使用 SimpleMarkdown */}
                    <SimpleMarkdown text={apiResult?.agent_summary?.final_recommendation} />
                  </GlassCard>

                  {/* 購物清單 */}
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                    {(apiResult?.agent_summary?.budget_items || []).map((item, i) => (
                      <GlassCard key={i} className="p-4 flex gap-4 items-center hover:bg-white/10 transition-colors group">
                        <div className="w-20 h-20 rounded-xl bg-white/5 shrink-0 overflow-hidden border border-white/10">
                           {item.image ? <img src={item.image} className="w-full h-full object-contain bg-white" alt={item.name} /> : <Shirt className="m-auto mt-6 text-gray-600" />}
                        </div>
                        <div className="flex-1 min-w-0">
                          <h4 className="font-bold text-sm truncate text-white mb-1 group-hover:text-purple-300 transition-colors">{item.name}</h4>
                          <p className="text-xs text-gray-500 mb-3">{item.seller}</p>
                          <div className="flex justify-between items-end">
                             <span className="text-cyan-300 font-mono font-bold text-lg">{item.currency} {item.price}</span>
                             {item.link && (
                               <a 
                                 href={item.link} 
                                 target="_blank" 
                                 rel="noreferrer" 
                                 className="text-xs bg-white text-black px-4 py-2 rounded-full font-bold hover:bg-purple-400 hover:text-white transition-all flex items-center gap-1 shadow-lg shadow-purple-500/20"
                               >
                                 Buy Now <ExternalLink size={12} />
                               </a>
                             )}
                          </div>
                        </div>
                      </GlassCard>
                    ))}
                  </div>

                   {/* Chat Input */}
                   <GlassCard className="flex-1 min-h-[300px] flex flex-col">
                     <div className="p-4 border-b border-white/10 font-semibold text-sm">Ask about this look</div>
                     <div className="flex-1 p-4 overflow-y-auto space-y-4 max-h-[300px]">
                       {chatHistory.map((msg, i) => <ChatMessage key={i} {...msg} />)}
                       <div ref={chatEndRef} />
                     </div>
                     <div className="p-4 border-t border-white/10">
                       <form onSubmit={handleSendMessage} className="flex gap-2">
                         <input 
                           type="text" 
                           value={chatInput}
                           onChange={(e) => setChatInput(e.target.value)}
                           placeholder="Ask why this outfit works..."
                           className="flex-1 bg-black/20 border border-white/10 rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-purple-500/50 text-white placeholder-gray-500"
                         />
                         <button 
                           type="submit"
                           className="p-3 rounded-xl bg-purple-600 hover:bg-purple-500 text-white transition-colors"
                         >
                           <Send className="w-4 h-4" />
                         </button>
                       </form>
                     </div>
                   </GlassCard>
                </div>
              </div>
            </motion.div>
          )}

        </AnimatePresence>
      </main>

      <style>{`
        @keyframes gradient-xy {
          0%, 100% {
              background-size: 400% 400%;
              background-position: left center;
          }
          50% {
              background-size: 200% 200%;
              background-position: right center;
          }
        }
        .animate-gradient-xy {
          animation: gradient-xy 6s ease infinite;
        }
      `}</style>
    </div>
  );
}