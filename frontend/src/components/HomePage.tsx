import { useState } from 'react';
import { Github, Mail, CheckCircle2 } from 'lucide-react';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';
import { Alert, AlertDescription } from './ui/alert';
import { toast } from 'sonner@2.0.3';

const HARDCODED_EMAIL = 'devabhixda@gmail.com';

export function HomePage() {
  const [repoUrl, setRepoUrl] = useState('');
  const [isIngesting, setIsIngesting] = useState(false);
  const [showSuccess, setShowSuccess] = useState(false);

  const handleIngest = async () => {
    if (!repoUrl.trim()) {
      toast.error('Please enter a repository URL');
      return;
    }

    // Validate GitHub URL (supports both HTTPS and SSH formats)
    const httpsPattern = /^https?:\/\/(www\.)?github\.com\/[\w-]+\/[\w.-]+\/?$/;
    const sshPattern = /^git@github\.com:[\w-]+\/[\w.-]+\.git$/;
    
    if (!httpsPattern.test(repoUrl.trim()) && !sshPattern.test(repoUrl.trim())) {
      toast.error('Please enter a valid GitHub repository URL (HTTPS or SSH format)');
      return;
    }

    setIsIngesting(true);
    setShowSuccess(false);

    try {
      const response = await fetch('/api/ingest', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ 
          repo_url: repoUrl.trim(),
          user_email: HARDCODED_EMAIL
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        console.error('Ingestion API error:', data);
        throw new Error(data.error || 'Failed to submit repository');
      }
      
      setShowSuccess(true);
      setRepoUrl('');
      toast.success('Repository submitted for ingestion');
    } catch (error) {
      console.error('Failed to submit repository:', error);
      toast.error(error instanceof Error ? error.message : 'Failed to submit repository. Please try again.');
    } finally {
      setIsIngesting(false);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !isIngesting) {
      handleIngest();
    }
  };

  return (
    <div className="min-h-screen bg-muted/30">
      {/* Header */}
      <header className="border-b bg-background">
        <div className="container mx-auto px-4 py-4 flex items-center justify-between max-w-4xl">
          <div className="flex items-center gap-2">
            <Github className="h-6 w-6" />
            <span>Peyote</span>
          </div>
          <div className="flex items-center gap-2 text-muted-foreground">
            <Mail className="h-4 w-4" />
            <span className="hidden sm:inline">{HARDCODED_EMAIL}</span>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="container mx-auto px-4 py-8 max-w-4xl">
        <div className="space-y-6">
          <div>
            <h1>Ingest Repository</h1>
            <p className="text-muted-foreground">
              Enter a GitHub repository URL to start the ingestion process
            </p>
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Repository URL</CardTitle>
              <CardDescription>
                Enter the full URL of the GitHub repository you want to ingest
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="repo-url">GitHub Repository URL</Label>
                <Input
                  id="repo-url"
                  type="text"
                  placeholder="git@github.com:username/repository.git"
                  value={repoUrl}
                  onChange={(e) => setRepoUrl(e.target.value)}
                  onKeyPress={handleKeyPress}
                  disabled={isIngesting}
                />
              </div>

              <Button
                onClick={handleIngest}
                disabled={isIngesting || !repoUrl.trim()}
                className="w-full sm:w-auto"
              >
                {isIngesting ? 'Submitting...' : 'Ingest Repository'}
              </Button>

              {showSuccess && (
                <Alert className="border-green-200 bg-green-50 dark:bg-green-950/20 dark:border-green-900">
                  <CheckCircle2 className="h-4 w-4 text-green-600 dark:text-green-400" />
                  <AlertDescription className="text-green-800 dark:text-green-300">
                    <div className="flex items-start gap-2">
                      <Mail className="h-4 w-4 mt-0.5 flex-shrink-0" />
                      <div>
                        <div>Repository submitted successfully!</div>
                        <div className="mt-1 text-green-700 dark:text-green-400">
                          You'll be notified via email at <span className="font-medium">{HARDCODED_EMAIL}</span> once the ingestion is complete.
                        </div>
                      </div>
                    </div>
                  </AlertDescription>
                </Alert>
              )}
            </CardContent>
          </Card>

          <Card className="bg-muted/50">
            <CardHeader>
              <CardTitle>How it works</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              <div className="flex gap-3">
                <div className="flex h-6 w-6 items-center justify-center rounded-full bg-primary text-primary-foreground flex-shrink-0">
                  1
                </div>
                <p>Enter the GitHub repository URL you want to ingest</p>
              </div>
              <div className="flex gap-3">
                <div className="flex h-6 w-6 items-center justify-center rounded-full bg-primary text-primary-foreground flex-shrink-0">
                  2
                </div>
                <p>Click "Ingest Repository" to submit your request</p>
              </div>
              <div className="flex gap-3">
                <div className="flex h-6 w-6 items-center justify-center rounded-full bg-primary text-primary-foreground flex-shrink-0">
                  3
                </div>
                <p>We'll process your repository and notify you via email when complete</p>
              </div>
            </CardContent>
          </Card>
        </div>
      </main>
    </div>
  );
}
