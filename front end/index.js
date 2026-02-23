import React, { useState, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
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
  Bot
} from 'lucide-react';

// --- Mock Data ---
const MOCK_RESULT = {
  outfit_score: 98,
  vibe_match: "Neo-Tokyo Streetwear",
  color_palette: ["#E0B0FF", "#00FFFF", "#1A1A1A", "#FF00FF"],
  analysis: [
    { label: "Silhouette", value: "Oversized / Boxy", score: 92 },
    { label: "Texture Match", value: "Leather + Techwear", score: 88 },
    { label: "Seasonality", value: "FW 2025", score: 95 }
  ],
  items: [
    { name: "Cyber-Bomber Jacket", brand: "Acronym X", price: "$450" },
    { name: "Utility Cargo", brand: "Stone Island", price: "$320" },
  ]
};

// --- Components ---

const GlassCard = ({ children, className = "", delay = 0 }) => (
  <motion.div 
    initial={{ opacity: 0, y: 20 }}
    animate={{ opacity: 1, y: 0 }}
    transition={{ duration: 0.5, delay, ease: "easeOut" }}
    className={`relative overflow-hidden rounded-3xl border border-white/10 bg-white/5 backdrop-blur-xl shadow-2xl ${className}`}
  >
    {/* Shine effect */}
    <div className="absolute inset-0 bg-gradient-to-br from-white/5 to-transparent pointer-events-none" />
    <div className="relative z-10 h-full">
      {children}
    </div>
  </motion.div>
);

const Pill = ({ label, active, onClick }) => (
  <button
    onClick={onClick}
    className={`px-6 py-2 rounded-full text-sm font-medium transition-all duration-300 border ${
      active 
        ? "bg-purple-500/20 border-purple-400 text-purple-200 shadow-[0_0_15px_rgba(168,85,247,0.3)]" 
        : "bg-white/5 border-white/10 text-gray-400 hover:bg-white/10 hover:border-white/20"
    }`}
  >
    {label}
  </button>
);

const ProgressBar = ({ label, percentage, color = "bg-purple-500" }) => (
  <div className="mb-4">
    <div className="flex justify-between text-xs font-medium text-gray-400 mb-1">
      <span>{label}</span>
      <span>{percentage}%</span>
    </div>
    <div className="h-2 w-full bg-white/10 rounded-full overflow-hidden">
      <motion.div 
        initial={{ width: 0 }}
        animate={{ width: `${percentage}%` }}
        transition={{ duration: 1, delay: 0.5 }}
        className={`h-full ${color} shadow-[0_0_10px_currentColor]`}
      />
    </div>
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
      {text}
    </div>
  </motion.div>
);

export default function FashionAIApp() {
  const [appState, setAppState] = useState('input'); // input, loading, result
  const [selectedStyle, setSelectedStyle] = useState('Streetwear');
  const [uploadedImage, setUploadedImage] = useState(null);
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef(null);
  
  // Chat State
  const [userRequest, setUserRequest] = useState('');
  const [chatInput, setChatInput] = useState('');
  const [chatHistory, setChatHistory] = useState([]);
  const chatEndRef = useRef(null);

  // Auto-scroll chat
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatHistory, appState]);

  // Simulation of "AI Processing"
  const handleGenerate = () => {
    if (!uploadedImage) return;
    setAppState('loading');
    
    // Seed the initial analysis message based on inputs
    const initialAnalysis = `I've analyzed your upload. Given your preference for ${selectedStyle} ${userRequest ? `and request for "${userRequest}"` : ''}, I've constructed a look that balances structural utility with modern aesthetics. The palette is derived from the mid-tones of your item to ensure cohesion.`;
    
    setTimeout(() => {
      setChatHistory([
        { role: 'ai', text: initialAnalysis }
      ]);
      setAppState('result');
    }, 3500);
  };

  const handleReset = () => {
    setAppState('input');
    setUploadedImage(null);
    setUserRequest('');
    setChatHistory([]);
  };

  const handleFile = (file) => {
    if (file) {
      const url = URL.createObjectURL(file);
      setUploadedImage(url);
    }
  };

  const handleSendMessage = (e) => {
    e.preventDefault();
    if (!chatInput.trim()) return;

    const newMsg = { role: 'user', text: chatInput };
    setChatHistory(prev => [...prev, newMsg]);
    setChatInput('');

    // Simulate AI response
    setTimeout(() => {
      setChatHistory(prev => [...prev, { 
        role: 'ai', 
        text: "That's a great adjustment. Swapping the textures would definitely lean more into the avant-garde aesthetic you mentioned. I can update the visualization if you'd like?" 
      }]);
    }, 1500);
  };

  return (
    <div className="min-h-screen w-full bg-[#0a0a0f] text-white font-sans selection:bg-purple-500/30 overflow-x-hidden">
      
      {/* Background Ambience */}
      <div className="fixed inset-0 pointer-events-none">
        <div className="absolute top-[-10%] left-[-10%] w-[50vw] h-[50vw] bg-purple-900/20 rounded-full blur-[120px]" />
        <div className="absolute bottom-[-10%] right-[-10%] w-[50vw] h-[50vw] bg-blue-900/10 rounded-full blur-[120px]" />
        <div className="absolute top-[20%] right-[20%] w-[30vw] h-[30vw] bg-pink-900/10 rounded-full blur-[100px]" />
        <div className="absolute inset-0 bg-[url('https://grainy-gradients.vercel.app/noise.svg')] opacity-20" />
      </div>

      <main className="relative z-10 max-w-7xl mx-auto px-4 py-8 lg:py-12 flex flex-col min-h-screen">
        
        {/* Header */}
        <header className="flex justify-between items-center mb-12">
          <div className="flex items-center gap-2">
            <div className="w-10 h-10 bg-gradient-to-tr from-purple-500 to-cyan-500 rounded-xl flex items-center justify-center shadow-lg shadow-purple-500/20">
              <Sparkles className="text-white w-6 h-6" />
            </div>
            <div>
              <h1 className="text-xl font-bold tracking-tight text-transparent bg-clip-text bg-gradient-to-r from-white to-gray-400">
                AURA <span className="font-light">STYLIST</span>
              </h1>
              <p className="text-[10px] uppercase tracking-[0.2em] text-gray-500">Gen-AI Fashion Engine v2.5</p>
            </div>
          </div>
          <button className="p-2 rounded-full bg-white/5 border border-white/10 hover:bg-white/10 transition-colors">
            <Maximize2 className="w-5 h-5 text-gray-400" />
          </button>
        </header>

        {/* Content Switcher */}
        <div className="flex-1 flex flex-col justify-center">
          <AnimatePresence mode="wait">
            
            {/* STATE: INPUT */}
            {appState === 'input' && (
              <motion.div 
                key="input"
                initial={{ opacity: 0, scale: 0.95 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, filter: "blur(10px)", scale: 1.05 }}
                transition={{ duration: 0.5 }}
                className="w-full max-w-5xl mx-auto"
              >
                <div className="text-center mb-10">
                  <h2 className="text-4xl md:text-6xl font-bold mb-4 bg-gradient-to-b from-white via-white to-gray-500 bg-clip-text text-transparent">
                    Redefine Your Wardrobe.
                  </h2>
                  <p className="text-gray-400 text-lg max-w-2xl mx-auto">
                    Upload a piece you love. Our AI orchestrates the perfect outfit around it using 2025 trend forecasting.
                  </p>
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 h-auto lg:h-[650px]">
                  
                  {/* Left: Upload Zone */}
                  <div className="lg:col-span-7 h-full">
                    <GlassCard className="h-full flex flex-col p-1 group cursor-pointer transition-all hover:border-purple-500/30">
                      <div 
                        className={`
                          flex-1 border-2 border-dashed rounded-[20px] transition-all duration-300 relative overflow-hidden
                          flex flex-col items-center justify-center
                          ${isDragging || uploadedImage ? 'border-purple-500/50 bg-purple-500/5' : 'border-white/10 hover:border-white/20 hover:bg-white/5'}
                        `}
                        onDragOver={(e) => { e.preventDefault(); setIsDragging(true); }}
                        onDragLeave={() => setIsDragging(false)}
                        onDrop={(e) => {
                          e.preventDefault();
                          setIsDragging(false);
                          handleFile(e.dataTransfer.files[0]);
                        }}
                        onClick={() => fileInputRef.current?.click()}
                      >
                        <input 
                          type="file" 
                          ref={fileInputRef}
                          className="hidden" 
                          accept="image/*"
                          onChange={(e) => handleFile(e.target.files[0])}
                        />

                        {uploadedImage ? (
                          <div className="relative w-full h-full">
                            <img src={uploadedImage} alt="Uploaded" className="w-full h-full object-cover" />
                            <div className="absolute inset-0 bg-gradient-to-t from-black/80 to-transparent flex items-end p-6">
                              <div className="flex items-center gap-2 text-white">
                                <CheckCircle2 className="text-green-400 w-5 h-5" />
                                <span className="font-medium">Image Uploaded Successfully</span>
                              </div>
                            </div>
                            <button 
                              onClick={(e) => { e.stopPropagation(); setUploadedImage(null); }}
                              className="absolute top-4 right-4 p-2 bg-black/50 backdrop-blur-md rounded-full text-white/70 hover:text-white"
                            >
                              <RefreshCcw className="w-4 h-4" />
                            </button>
                          </div>
                        ) : (
                          <div className="text-center p-8">
                            <div className="w-20 h-20 mx-auto bg-gradient-to-br from-purple-500/20 to-blue-500/10 rounded-full flex items-center justify-center mb-6 ring-1 ring-white/10">
                              <Upload className="w-8 h-8 text-purple-300" />
                            </div>
                            <h3 className="text-xl font-medium text-white mb-2">Drop your image here</h3>
                            <p className="text-gray-500 text-sm mb-6">Support for JPG, PNG (Max 10MB)</p>
                            <span className="inline-block px-4 py-2 rounded-lg bg-white/10 text-white/80 text-sm hover:bg-white/20 transition-colors">
                              Browse Files
                            </span>
                          </div>
                        )}
                      </div>
                    </GlassCard>
                  </div>

                  {/* Right: Controls */}
                  <div className="lg:col-span-5 flex flex-col gap-6">
                    <GlassCard className="flex-1 p-8 overflow-y-auto">
                      <div className="flex items-center gap-3 mb-6">
                        <Palette className="w-5 h-5 text-purple-400" />
                        <h3 className="text-lg font-semibold">Style Preference</h3>
                      </div>
                      
                      <div className="flex flex-wrap gap-3 mb-8">
                        {['Streetwear', 'Minimalist', 'Y2K', 'Luxury', 'Avant-Garde', 'Techwear'].map((style) => (
                          <Pill 
                            key={style} 
                            label={style} 
                            active={selectedStyle === style} 
                            onClick={() => setSelectedStyle(style)} 
                          />
                        ))}
                      </div>

                      <div className="flex items-center gap-3 mb-4">
                        <MessageSquare className="w-5 h-5 text-cyan-400" />
                        <h3 className="text-lg font-semibold">Special Request</h3>
                      </div>
                      <div className="mb-6">
                         <textarea 
                           value={userRequest}
                           onChange={(e) => setUserRequest(e.target.value)}
                           placeholder="Ex: 'I need an outfit for a tech gallery opening in Berlin. Keep it monochromatic.'"
                           className="w-full h-32 bg-white/5 border border-white/10 rounded-xl p-4 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-purple-500/50 resize-none transition-colors"
                         />
                      </div>
                    </GlassCard>

                    <button
                      onClick={handleGenerate}
                      disabled={!uploadedImage}
                      className={`
                        relative group overflow-hidden w-full p-1 rounded-2xl transition-all duration-300
                        ${!uploadedImage ? 'opacity-50 grayscale cursor-not-allowed' : 'hover:shadow-[0_0_40px_rgba(168,85,247,0.4)]'}
                      `}
                    >
                      <div className="absolute inset-0 bg-gradient-to-r from-purple-600 via-pink-600 to-blue-600 animate-gradient-xy" />
                      <div className="relative bg-[#0a0a0f] rounded-[14px] px-8 py-5 flex items-center justify-center gap-3 group-hover:bg-opacity-90 transition-all">
                        <span className="text-lg font-bold bg-gradient-to-r from-white to-gray-200 bg-clip-text text-transparent">
                          GENERATE LOOK
                        </span>
                        <Zap className="w-5 h-5 text-yellow-300 fill-yellow-300" />
                      </div>
                    </button>
                  </div>

                </div>
              </motion.div>
            )}

            {/* STATE: LOADING */}
            {appState === 'loading' && (
              <motion.div
                key="loading"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0, y: -20 }}
                className="flex flex-col items-center justify-center h-[600px]"
              >
                <div className="relative w-64 h-64 mb-8">
                  {/* Rotating Rings */}
                  <motion.div 
                    animate={{ rotate: 360 }}
                    transition={{ duration: 3, repeat: Infinity, ease: "linear" }}
                    className="absolute inset-0 rounded-full border border-t-purple-500 border-r-transparent border-b-cyan-500 border-l-transparent opacity-50"
                  />
                  <motion.div 
                    animate={{ rotate: -180 }}
                    transition={{ duration: 4, repeat: Infinity, ease: "linear" }}
                    className="absolute inset-4 rounded-full border border-t-transparent border-r-pink-500 border-b-transparent border-l-purple-500 opacity-50"
                  />
                  
                  {/* Center Pulse */}
                  <div className="absolute inset-0 flex items-center justify-center">
                    <div className="w-40 h-40 rounded-full bg-purple-500/10 backdrop-blur-md flex items-center justify-center relative overflow-hidden">
                       <ScanLine className="w-12 h-12 text-white/50 animate-pulse" />
                       <motion.div 
                        animate={{ top: ["0%", "100%"] }}
                        transition={{ duration: 1.5, repeat: Infinity, ease: "linear" }}
                        className="absolute left-0 right-0 h-[2px] bg-cyan-400 shadow-[0_0_15px_#06b6d4]"
                       />
                    </div>
                  </div>
                </div>
                
                <h3 className="text-2xl font-light tracking-widest text-white mb-2">ANALYZING WARDROBE</h3>
                <motion.p 
                  animate={{ opacity: [0.5, 1, 0.5] }}
                  transition={{ duration: 2, repeat: Infinity }}
                  className="text-purple-300 text-sm font-mono"
                >
                  Matching textures... Parsing {selectedStyle} trends...
                </motion.p>
              </motion.div>
            )}

            {/* STATE: RESULT */}
            {appState === 'result' && (
              <motion.div
                key="result"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="w-full max-w-7xl mx-auto"
              >
                <div className="flex justify-between items-end mb-8">
                  <div>
                    <h2 className="text-3xl font-bold text-white mb-1">Your Curated Look</h2>
                    <div className="flex items-center gap-2 text-gray-400 text-sm">
                      <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
                      AI Confidence Score: 98%
                    </div>
                  </div>
                  <button 
                    onClick={handleReset}
                    className="px-4 py-2 rounded-lg border border-white/10 hover:bg-white/10 text-sm transition-colors flex items-center gap-2"
                  >
                    <RefreshCcw className="w-4 h-4" /> Start Over
                  </button>
                </div>

                <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 h-auto">
                  
                  {/* Column 1: The Input Image & DNA */}
                  <div className="space-y-6 flex flex-col h-[700px]">
                    <GlassCard className="p-1 h-1/3 relative group">
                      <img src={uploadedImage} alt="Input" className="w-full h-full object-cover rounded-2xl opacity-60 group-hover:opacity-100 transition-opacity" />
                      <div className="absolute bottom-3 left-3 px-3 py-1 rounded-full bg-black/60 backdrop-blur-md text-xs border border-white/10">Input Source</div>
                    </GlassCard>

                    <GlassCard className="flex-1 p-6 relative overflow-hidden flex flex-col justify-center" delay={0.1}>
                      <div className="absolute top-0 right-0 p-3 opacity-20">
                         <Zap className="w-24 h-24 text-white" />
                      </div>
                      <h3 className="text-lg font-semibold mb-6 flex items-center gap-2">
                        Fashion DNA <div className="h-px flex-1 bg-white/10" />
                      </h3>
                      
                      <div className="space-y-6">
                        {MOCK_RESULT.analysis.map((item, idx) => (
                           <ProgressBar key={idx} label={item.label} percentage={item.score} />
                        ))}
                      </div>

                      <div className="mt-8">
                        <p className="text-xs font-medium text-gray-400 mb-3">COLOR HARMONY</p>
                        <div className="flex gap-2">
                          {MOCK_RESULT.color_palette.map((color, idx) => (
                            <motion.div 
                              key={idx}
                              initial={{ scale: 0 }}
                              animate={{ scale: 1 }}
                              transition={{ delay: 0.5 + (idx * 0.1) }}
                              className="w-10 h-10 rounded-full border border-white/10 shadow-lg relative group"
                              style={{ backgroundColor: color }}
                            >
                               <div className="absolute -bottom-8 left-1/2 -translate-x-1/2 bg-black text-xs px-2 py-1 rounded opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap z-20">
                                 {color}
                               </div>
                            </motion.div>
                          ))}
                        </div>
                      </div>
                    </GlassCard>
                  </div>

                  {/* Column 2: The Generated Hero Image */}
                  <GlassCard className="lg:col-span-2 p-1 relative group h-[700px]" delay={0.2}>
                    <div className="absolute inset-0 bg-gradient-to-b from-transparent via-transparent to-black/80 z-10" />
                    
                    {/* Placeholder for Generated Image */}
                    <div className="w-full h-full rounded-[22px] bg-gray-800 overflow-hidden relative">
                        {/* In a real app, this is the AI result URL */}
                        <img 
                          src="https://images.unsplash.com/photo-1596706782806-613d29a676c8?q=80&w=2070&auto=format&fit=crop" 
                          alt="Generated Outfit" 
                          className="w-full h-full object-cover transform group-hover:scale-105 transition-transform duration-700"
                        />
                        
                        {/* Floating "AI Tags" on the image */}
                        <motion.div 
                          initial={{ opacity: 0, x: 20 }}
                          animate={{ opacity: 1, x: 0 }}
                          transition={{ delay: 1 }}
                          className="absolute top-10 right-10 z-20 flex flex-col gap-2 items-end"
                        >
                           <div className="bg-black/40 backdrop-blur-md px-4 py-2 rounded-lg border border-white/10 text-xs font-mono text-cyan-300">
                             BRAND: ACRONYM
                           </div>
                           <div className="bg-black/40 backdrop-blur-md px-4 py-2 rounded-lg border border-white/10 text-xs font-mono text-purple-300">
                             FABRIC: GORE-TEX PRO
                           </div>
                        </motion.div>
                    </div>

                    <div className="absolute bottom-0 left-0 right-0 p-8 z-20">
                      <div className="flex justify-between items-end">
                        <div>
                          <motion.h2 
                            initial={{ y: 20, opacity: 0 }}
                            animate={{ y: 0, opacity: 1 }}
                            transition={{ delay: 0.4 }}
                            className="text-4xl font-bold mb-2 text-white"
                          >
                            {MOCK_RESULT.vibe_match}
                          </motion.h2>
                          <p className="text-gray-300 max-w-md text-sm">
                            A curated fusion of tech-utility and street aesthetics, perfectly balancing your preference for {selectedStyle}.
                          </p>
                        </div>
                        <button className="bg-white text-black px-6 py-3 rounded-full font-bold hover:scale-105 transition-transform flex items-center gap-2">
                           <Share2 className="w-4 h-4" /> Share Look
                        </button>
                      </div>
                    </div>
                  </GlassCard>

                </div>

                {/* Bottom Strip: Shop & Chat */}
                <div className="mt-6 grid grid-cols-1 lg:grid-cols-2 gap-6 h-[400px]">
                   {/* Shop Section */}
                   <div className="flex flex-col gap-4 overflow-y-auto pr-2">
                     <h3 className="text-lg font-semibold flex items-center gap-2 mb-2">
                       <Shirt className="w-5 h-5 text-purple-400" /> Shop the Look
                     </h3>
                     {MOCK_RESULT.items.map((item, idx) => (
                        <GlassCard key={idx} className="p-4 flex items-center justify-between shrink-0" delay={0.6 + (idx * 0.1)}>
                          <div className="flex items-center gap-4">
                            <div className="w-12 h-12 rounded-lg bg-white/5 flex items-center justify-center">
                              <Shirt className="text-gray-400" />
                            </div>
                            <div>
                              <h4 className="font-medium text-white">{item.name}</h4>
                              <p className="text-xs text-gray-500 uppercase tracking-wider">{item.brand}</p>
                            </div>
                          </div>
                          <span className="text-purple-300 font-mono">{item.price}</span>
                        </GlassCard>
                     ))}
                   </div>

                   {/* Chat Interface */}
                   <GlassCard className="flex flex-col" delay={0.8}>
                     <div className="p-4 border-b border-white/10 bg-white/5 flex items-center gap-2">
                       <Bot className="w-5 h-5 text-cyan-400" />
                       <span className="font-semibold text-sm">Stylist Assistant</span>
                     </div>
                     
                     {/* Chat Messages */}
                     <div className="flex-1 p-4 overflow-y-auto space-y-4">
                        {chatHistory.map((msg, idx) => (
                          <ChatMessage key={idx} role={msg.role} text={msg.text} />
                        ))}
                        <div ref={chatEndRef} />
                     </div>

                     {/* Chat Input */}
                     <div className="p-4 border-t border-white/10 bg-white/5">
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
              </motion.div>
            )}

          </AnimatePresence>
        </div>
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