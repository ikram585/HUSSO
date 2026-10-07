using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using TELSEFA.Security;

namespace TELSEFA
{
    public partial class LoginWindow : Window
    {
        public LoginWindow()
        {
            InitializeComponent();
            _ = PasswordBox.Focus();
        }

        private void LoginButton_Click(object sender, RoutedEventArgs e)
        {
            var username = UsernameBox.Text.Trim();
            var password = PasswordBox.Password;

            if (string.IsNullOrEmpty(username) || string.IsNullOrEmpty(password))
            {
                ShowMessage("Kullanici adi ve sifre giriniz.", Brushes.Red);
                return;
            }

            LoginButton.IsEnabled = false;
            LoginButton.Content = "Kontrol ediliyor...";

            var (ok, message, user) = Security.Authenticate(username, password);

            if (!ok)
            {
                LoginButton.IsEnabled = true;
                LoginButton.Content = "GIRIS YAP";
                ShowMessage(message, Brushes.Red);
                PasswordBox.Clear();
                PasswordBox.Focus();
                return;
            }

            Security.CurrentUser = user;
            ShowMessage("", Brushes.Green);

            var mainWindow = new MainWindow();
            mainWindow.Show();
            Close();
        }

        private void ClearButton_Click(object sender, RoutedEventArgs e)
        {
            UsernameBox.Clear();
            PasswordBox.Clear();
            MessageText.Text = "";
            UsernameBox.Focus();
        }

        private void ExitButton_Click(object sender, RoutedEventArgs e)
        {
            Application.Current.Shutdown();
        }

        private void ThemeButton_Click(object sender, RoutedEventArgs e)
        {
            MessageBox.Show("Tema destegi yakinda eklenecek.", "Bilgi", MessageBoxButton.OK, MessageBoxImage.Information);
        }

        private void ForgotButton_Click(object sender, RoutedEventArgs e)
        {
            MessageBox.Show(
                "Sifrenizi sifirlamak icin yonetici hesabiyla giris yapip Kullanicilar bolumunden sifre sifirlayabilirsiniz.",
                "Sifremi Unuttum", MessageBoxButton.OK, MessageBoxImage.Information);
        }

        private void ShowMessage(string text, Brush color)
        {
            MessageText.Text = text;
            MessageText.Foreground = color;
            MessageText.FontWeight = FontWeights.SemiBold;
        }
    }
}
