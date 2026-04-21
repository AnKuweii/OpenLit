import { useState } from "react";
import { Header } from "./components/Header";
import { ChatInterface } from "./components/ChatInterface";
import { PDFPanel } from "./components/PDFPanel";
import { Toaster } from "./components/ui/sonner";
import { ParticleCanvas } from "./components/ParticleCanvas";

export default function App() {
  const [chatKey, setChatKey] = useState(0);
  const [currentFileId, setCurrentFileId] = useState<string>('');
  const [currentFileName, setCurrentFileName] = useState<string>('');
  const [currentTotalPages, setCurrentTotalPages] = useState<number>(0);

  const handleClearChat = () => {
    setChatKey((prev) => prev + 1);
  };

  const handleFileReady = (fileId: string, fileName: string, totalPages: number) => {
    setCurrentFileId(fileId);
    setCurrentFileName(fileName);  
    setCurrentTotalPages(totalPages);
  };

  return (
    <div className="dark min-h-screen bg-background text-foreground relative overflow-hidden">
      <ParticleCanvas />
      <div className="background-system">
        <div className="floating-elements">
          <div className="floating-orb floating-orb-1"></div>
          <div className="floating-orb floating-orb-2"></div>
          <div className="floating-orb floating-orb-3"></div>
          <div className="floating-orb floating-orb-4"></div>
        </div>

        <div className="geometric-decorations">
          <div className="geometric-line geometric-line-1"></div>
          <div className="geometric-line geometric-line-2"></div>
          <div className="geometric-line geometric-line-3"></div>
          <div className="geometric-polygon geometric-polygon-1"></div>
          <div className="geometric-polygon geometric-polygon-2"></div>
          <div className="geometric-circle geometric-circle-1"></div>
          <div className="geometric-circle geometric-circle-2"></div>
        </div>

        <div className="particle-system">
          {Array.from({ length: 15 }).map((_, i) => (
            <div key={i} className={`particle particle-${i + 1}`}></div>
          ))}
        </div>

        <div className="light-beams">
          <div className="light-beam light-beam-1"></div>
          <div className="light-beam light-beam-2"></div>
          <div className="light-beam light-beam-3"></div>
        </div>

        <div className="grid-overlay"></div>
      </div>

      <div className="relative z-10">
        <div className="h-screen flex flex-col">
          <div className="max-w-7xl mx-auto w-full">
            <Header />
          </div>

          <div className="flex-1 grid grid-cols-1 lg:grid-cols-[1.5fr_1fr] gap-5 min-h-0 px-5 pb-5">
            <div className="flex flex-col min-h-0">
              <ChatInterface
                key={chatKey}
                onClearChat={handleClearChat}
                fileId={currentFileId}
                fileName={currentFileName}
              />
            </div>

            <div className="flex flex-col min-h-0">
              <PDFPanel 
                onFileReady={handleFileReady}
              />
            </div>
          </div>
        </div>
      </div>

      <Toaster 
        position="top-right"
        expand={false}
        richColors
        closeButton
        theme="dark"
      />
    </div>
  );
}
