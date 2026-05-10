import { Switch, Route } from "wouter";
import NotFound from "@/pages/not-found";
import Login from "@/pages/login";
import Dashboard from "@/pages/dashboard";

function AppWrapper() {
  return (
    <Switch>
      <Route path="/login" component={Login} />
      <Route path="/coding" component={Dashboard} />
      <Route path="/redteam" component={Dashboard} />
      <Route path="/osint" component={Dashboard} />
      <Route path="/reports" component={Dashboard} />
      <Route path="/tutor" component={Dashboard} />
      <Route path="/agents" component={Dashboard} />
      <Route path="/" component={Dashboard} />
      <Route component={NotFound} />
    </Switch>
  );
}

export default AppWrapper;
