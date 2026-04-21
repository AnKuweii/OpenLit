import { useState, useRef, useEffect } from "react";
import { Button } from "./ui/button";
import { Badge } from "./ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "./ui/tabs";
import { Progress } from "./ui/progress";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "./ui/dialog";
import { ScrollArea } from "./ui/scroll-area";
import { 
  Upload, 
  FileText, 
  ChevronLeft, 
  ChevronRight, 
  AlertCircle, 
  CheckCircle2,
  Loader2,
  RefreshCw,
  File,
  Sparkles,
} from "lucide-react";
import { uploadPdf, startParse, subscribePdfStatus, buildIndex, getPdfPageUrl, getSummary } from "../services/api";
import { toast } from "sonner";

type UploadStatus = 'idle' | 'uploading' | 'parsing' | 'ready' | 'error';

interface PDFPanelProps {
  className?: string;
  onFileReady?: (fileId: string, fileName: string, totalPages: number) => void;
}

export function PDFPanel({ className, onFileReady }: PDFPanelProps) {
  const [uploadStatus, setUploadStatus] = useState<UploadStatus>('idle');
  const [fileName, setFileName] = useState<string>('');
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(0);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [fileId, setFileId] = useState<string>('');
  const [errorMessage, setErrorMessage] = useState<string>('');
  const [summaryOpen, setSummaryOpen] = useState(false);
  const [summaryText, setSummaryText] = useState<string>('');
  const [summaryLoading, setSummaryLoading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const statusSource = useRef<EventSource | null>(null);

  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file || !file.type.includes('pdf')) {
      toast.error('Please select a valid PDF file');
      return;
    }

    setFileName(file.name);
    setUploadStatus('uploading');
    setUploadProgress(0);
    setErrorMessage('');

    let progressInterval: ReturnType<typeof setInterval> | undefined;

    try {
      progressInterval = setInterval(() => {
        setUploadProgress(prev => Math.min(prev + 15, 90));
      }, 200);

      const uploadResponse = await uploadPdf(file);
      clearInterval(progressInterval);
      setUploadProgress(100);
      
      setFileId(uploadResponse.fileId);
      setTotalPages(uploadResponse.pages);
      setCurrentPage(1);

      toast.success('PDF uploaded successfully');

      setUploadStatus('parsing');
      setUploadProgress(0);
      await startParse(uploadResponse.fileId);

      startStatusStream(uploadResponse.fileId);

    } catch (error) {
      console.error('Upload failed:', error);
      
      if (error instanceof TypeError && error.message.includes('Failed to fetch')) {
        const mockFileId = `demo_${Date.now()}`;
        const mockPages = 8;
        
        if (progressInterval) clearInterval(progressInterval);
        setUploadProgress(100);
        setFileId(mockFileId);
        setTotalPages(mockPages);
        setCurrentPage(1);
        
        setTimeout(() => {
          setUploadStatus('parsing');
          setUploadProgress(0);
          
          const parseInterval = setInterval(() => {
            setUploadProgress(prev => {
              if (prev >= 100) {
                clearInterval(parseInterval);
                setUploadStatus('ready');
                toast.success('Document processed successfully (Demo Mode)');
                onFileReady?.(mockFileId, fileName, mockPages);
                return 100;
              }
              return prev + 20;
            });
          }, 500);
        }, 1000);
        
        toast.success('PDF uploaded successfully (Demo Mode)');
        return;
      }
      
      setUploadStatus('error');
      setErrorMessage(error instanceof Error ? error.message : 'Upload failed');
      toast.error('Failed to upload PDF');
    }
  };

  const startStatusStream = (fileId: string) => {
    statusSource.current?.close();

    statusSource.current = subscribePdfStatus(
      fileId,
      async (status) => {
        setUploadProgress(status.progress);

        if (status.status === 'ready') {
          setUploadStatus('ready');

          try {
            await buildIndex(fileId);
            toast.success('Document processed and indexed successfully');
            onFileReady?.(fileId, fileName, totalPages);
          } catch (indexError) {
            console.error('Index build failed:', indexError);
            toast.error('Document processed but indexing failed');
          }
        } else if (status.status === 'error') {
          setUploadStatus('error');
          setErrorMessage(status.errorMsg || 'Parsing failed');
          toast.error('Failed to process document');
        }
      },
      () => {
        setUploadStatus('error');
        setErrorMessage('Lost connection to server');
      },
    );
  };

  useEffect(() => {
    return () => {
      statusSource.current?.close();
    };
  }, []);

  const handleUploadClick = () => {
    fileInputRef.current?.click();
  };

  const handleReplace = () => {
    statusSource.current?.close();

    setUploadStatus('idle');
    setFileName('');
    setCurrentPage(1);
    setTotalPages(0);
    setUploadProgress(0);
    setFileId('');
    setErrorMessage('');
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleSummary = async () => {
    if (!fileId) return;
    setSummaryLoading(true);
    setSummaryText('');
    setSummaryOpen(true);
    try {
      const res = await getSummary(fileId);
      setSummaryText(res.summary);
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'Failed to generate summary';
      toast.error(msg);
      setSummaryText(`Error: ${msg}`);
    } finally {
      setSummaryLoading(false);
    }
  };

  const nextPage = () => {
    if (currentPage < totalPages) {
      setCurrentPage(prev => prev + 1);
    }
  };

  const prevPage = () => {
    if (currentPage > 1) {
      setCurrentPage(prev => prev - 1);
    }
  };

  const getStatusIcon = () => {
    switch (uploadStatus) {
      case 'uploading':
      case 'parsing':
        return <Loader2 className="w-3.5 h-3.5 animate-spin" />;
      case 'ready':
        return <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />;
      case 'error':
        return <AlertCircle className="w-3.5 h-3.5 text-rose-400" />;
      default:
        return <FileText className="w-3.5 h-3.5" />;
    }
  };

  const getStatusText = () => {
    switch (uploadStatus) {
      case 'uploading':
        return 'Uploading...';
      case 'parsing':
        return 'Parsing document...';
      case 'ready':
        return 'Ready';
      case 'error':
        return 'Error';
      default:
        return 'No document';
    }
  };

  const getStatusVariant = (): "default" | "secondary" | "destructive" | "outline" => {
    switch (uploadStatus) {
      case 'ready':
        return 'default';
      case 'error':
        return 'destructive';
      case 'uploading':
      case 'parsing':
        return 'secondary';
      default:
        return 'outline';
    }
  };

  return (
    <div className={`glass-panel-bright h-full flex flex-col relative overflow-hidden ${className}`}>
      <div className="absolute inset-0 opacity-[0.03]">
        <div className="absolute inset-0 bg-gradient-to-br from-emerald-500/20 via-transparent to-amber-500/15"></div>
      </div>

      <div className="relative px-5 py-4 border-b border-border/50">
        <div className="flex items-center justify-between mb-3">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-xl bg-emerald-500/10 border border-emerald-500/25">
              <File className="w-4 h-4 text-emerald-400" />
            </div>
            <div>
              <h2 className="elegant-title text-base">Document</h2>
            </div>
          </div>
          <Badge variant={getStatusVariant()} className="flex items-center gap-1.5 px-2.5 py-1 text-xs">
            {getStatusIcon()}
            <span>{getStatusText()}</span>
          </Badge>
        </div>

        {uploadStatus === 'idle' ? (
          <Button 
            onClick={handleUploadClick} 
            className="w-full bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-600 hover:to-teal-700 text-white border border-emerald-500/30 rounded-xl transition-all duration-200 min-h-[44px] h-[44px] text-sm font-semibold cursor-pointer"
            style={{ boxShadow: '0 4px 16px rgba(16, 185, 129, 0.2)' }}
          >
            <Upload className="w-4 h-4 mr-2 flex-shrink-0" />
            <span className="flex-shrink-0">Upload PDF</span>
          </Button>
        ) : (
          <div className="flex gap-2">
            <div className="flex-1 text-sm text-muted-foreground truncate bg-secondary/30 p-3 rounded-xl border border-border/30 min-h-[44px] flex items-center">
              {fileName}
            </div>
            <Button 
              variant="outline" 
              size="sm" 
              onClick={handleReplace}
              className="shrink-0 min-h-[44px] h-[44px] w-[44px] p-0 border-border/30 hover:bg-destructive/10 transition-all duration-200 rounded-xl"
            >
              <RefreshCw className="w-4 h-4" />
            </Button>
          </div>
        )}

        {(uploadStatus === 'uploading' || uploadStatus === 'parsing') && (
          <div className="mt-3">
            <Progress value={uploadProgress} className="h-1.5" />
            <p className="text-xs text-muted-foreground/70 mt-1.5">
              {uploadStatus === 'uploading' 
                ? `Uploading... ${uploadProgress}%` 
                : `Processing document... ${uploadProgress}%`}
            </p>
          </div>
        )}

        {uploadStatus === 'error' && errorMessage && (
          <div className="mt-3 p-2.5 bg-destructive/8 border border-destructive/20 rounded-xl">
            <p className="text-xs text-destructive">{errorMessage}</p>
          </div>
        )}

        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf"
          onChange={handleFileUpload}
          className="hidden"
        />
      </div>

      {uploadStatus === 'ready' ? (
        <div className="flex-1 flex flex-col relative min-h-0">
          <Tabs defaultValue="original" className="flex-1 flex flex-col min-h-0">
            <div className="px-5 pt-3 flex items-center gap-2">
              <TabsList className="grid flex-1 grid-cols-2 h-9 bg-secondary/30 border border-border/30 rounded-xl">
                <TabsTrigger value="original" className="text-xs px-2 py-1.5 rounded-lg data-[state=active]:bg-amber-500/12 data-[state=active]:text-amber-400 transition-all">
                  Original
                </TabsTrigger>
                <TabsTrigger value="parsed" className="text-xs px-2 py-1.5 rounded-lg data-[state=active]:bg-amber-500/12 data-[state=active]:text-amber-400 transition-all">
                  Parsed
                </TabsTrigger>
              </TabsList>

              <Dialog open={summaryOpen} onOpenChange={setSummaryOpen}>
                <DialogTrigger asChild>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleSummary}
                    disabled={summaryLoading}
                    className="h-9 px-3 shrink-0 border-border/30 hover:bg-violet-500/10 hover:text-violet-400 transition-all rounded-xl text-xs gap-1.5"
                  >
                    {summaryLoading ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <Sparkles className="w-3.5 h-3.5" />
                    )}
                    Summary
                  </Button>
                </DialogTrigger>
                <DialogContent className="sm:max-w-lg">
                  <DialogHeader>
                    <DialogTitle className="flex items-center gap-2">
                      <Sparkles className="w-4 h-4 text-violet-400" />
                      Document Summary
                    </DialogTitle>
                    <DialogDescription>
                      AI-generated summary of the uploaded document
                    </DialogDescription>
                  </DialogHeader>
                  <ScrollArea className="max-h-[60vh]">
                    {summaryLoading ? (
                      <div className="flex items-center justify-center py-12">
                        <Loader2 className="w-6 h-6 animate-spin text-violet-400" />
                        <span className="ml-3 text-sm text-muted-foreground">Generating summary...</span>
                      </div>
                    ) : (
                      <p className="text-sm leading-relaxed text-foreground/90 whitespace-pre-wrap pr-4">
                        {summaryText}
                      </p>
                    )}
                  </ScrollArea>
                </DialogContent>
              </Dialog>
            </div>
            
            <TabsContent value="original" className="flex-1 flex flex-col mt-3 mx-5 mb-4 min-h-0">
              <div className="flex-1 bg-stone-900/30 border border-border/40 rounded-xl flex items-center justify-center overflow-hidden">
                {fileId ? (
                  <img
                    src={getPdfPageUrl(fileId, currentPage, 'original')}
                    alt={`PDF Page ${currentPage}`}
                    className="max-w-full max-h-full object-contain"
                    onError={(e) => {
                      const target = e.target as HTMLImageElement;
                      target.style.display = 'none';
                      target.nextElementSibling?.classList.remove('hidden');
                    }}
                  />
                ) : null}
              </div>
            </TabsContent>
            
            <TabsContent value="parsed" className="flex-1 flex flex-col mt-3 mx-5 mb-4 min-h-0">
              <div className="flex-1 bg-stone-900/30 border border-border/40 rounded-xl flex items-center justify-center overflow-hidden">
                {fileId ? (
                  <img
                    src={getPdfPageUrl(fileId, currentPage, 'parsed')}
                    alt={`Parsed PDF Page ${currentPage}`}
                    className="max-w-full max-h-full object-contain"
                    onError={(e) => {
                      const target = e.target as HTMLImageElement;
                      target.style.display = 'none';
                      target.nextElementSibling?.classList.remove('hidden');
                    }}
                  />
                ) : null}
              </div>
            </TabsContent>
          </Tabs>

          <div className="px-5 py-4 border-t border-border/40 bg-card/25">
            <div className="flex items-center justify-between">
              <Button
                variant="outline"
                size="sm"
                onClick={prevPage}
                disabled={currentPage <= 1}
                className="h-9 px-3 border-border/30 hover:bg-amber-500/8 transition-all rounded-xl"
              >
                <ChevronLeft className="w-4 h-4" />
              </Button>
              
              <span className="text-xs text-muted-foreground font-medium tracking-wide">
                Page {currentPage} of {totalPages}
              </span>
              
              <Button
                variant="outline"
                size="sm"
                onClick={nextPage}
                disabled={currentPage >= totalPages}
                className="h-9 px-3 border-border/30 hover:bg-amber-500/8 transition-all rounded-xl"
              >
                <ChevronRight className="w-4 h-4" />
              </Button>
            </div>
          </div>
        </div>
      ) : (
        <div className="flex-1 flex items-center justify-center p-8 relative">
          <div className="text-center space-y-5 max-w-sm">
            {uploadStatus === 'idle' ? (
              <>
                <div className="w-18 h-18 bg-gradient-to-br from-emerald-500/10 to-teal-500/10 rounded-2xl flex items-center justify-center mx-auto border border-emerald-500/20" style={{ width: '72px', height: '72px' }}>
                  <Upload className="w-8 h-8 text-emerald-400/70" />
                </div>
                <div className="space-y-1.5">
                  <h3 className="font-semibold text-foreground text-sm">No document uploaded</h3>
                  <p className="text-xs text-muted-foreground/70 leading-relaxed">
                    Upload a PDF document to start analyzing and asking questions about its content.
                  </p>
                </div>
              </>
            ) : uploadStatus === 'error' ? (
              <>
                <div className="w-18 h-18 bg-rose-500/10 rounded-2xl flex items-center justify-center mx-auto border border-rose-500/20" style={{ width: '72px', height: '72px' }}>
                  <AlertCircle className="w-8 h-8 text-rose-400" />
                </div>
                <div className="space-y-1.5">
                  <h3 className="font-semibold text-foreground text-sm">Upload failed</h3>
                  <p className="text-xs text-muted-foreground/70">
                    There was an error processing your document. Please try again.
                  </p>
                </div>
              </>
            ) : (
              <>
                <div className="w-18 h-18 bg-amber-500/10 rounded-2xl flex items-center justify-center mx-auto border border-amber-500/20" style={{ width: '72px', height: '72px' }}>
                  <Loader2 className="w-8 h-8 text-amber-400 animate-spin" />
                </div>
                <div className="space-y-1.5">
                  <h3 className="font-semibold text-foreground text-sm">Processing document</h3>
                  <p className="text-xs text-muted-foreground/70">
                    {uploadStatus === 'uploading' 
                      ? 'Uploading your PDF file...' 
                      : 'Analyzing and parsing the document content...'}
                  </p>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
