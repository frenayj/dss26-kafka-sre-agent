import React from 'react';
import {NavigationContainer} from '@react-navigation/native';
import {createNativeStackNavigator} from '@react-navigation/native-stack';
import {QueryClient, QueryClientProvider} from '@tanstack/react-query';
import TransactionsScreen from './screens/TransactionsScreen';
import CardControlsScreen from './screens/CardControlsScreen';

const Stack = createNativeStackNavigator();
const queryClient = new QueryClient({defaultOptions: {queries: {staleTime: 30_000, retry: 1}}});

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <NavigationContainer>
        <Stack.Navigator>
          <Stack.Screen name="Transactions" component={TransactionsScreen as never} />
          <Stack.Screen name="CardControls" component={CardControlsScreen as never} options={{title: 'Card controls'}} />
        </Stack.Navigator>
      </NavigationContainer>
    </QueryClientProvider>
  );
}
