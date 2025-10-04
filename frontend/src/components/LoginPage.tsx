import { Github } from 'lucide-react';
import { Button } from './ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';
import { useAuth } from './AuthContext';

export function LoginPage() {
  const { signInWithGithub, isLoading } = useAuth();

  return (
    <div className="min-h-screen flex items-center justify-center bg-muted/30 p-4">
      <Card className="w-full max-w-md">
        <CardHeader className="space-y-1">
          <CardTitle>Welcome to Peyote</CardTitle>
          <CardDescription>
            Sign in with your GitHub account to get started
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Button
            onClick={signInWithGithub}
            disabled={isLoading}
            className="w-full"
            size="lg"
          >
            <Github className="mr-2 h-5 w-5" />
            {isLoading ? 'Signing in...' : 'Continue with GitHub'}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
